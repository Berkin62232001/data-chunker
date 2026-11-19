from utils.storage_paths import storage_path
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Tuple

from core.config import settings
from db import repository
from db.session import get_session
from models.chunk_models import Chunk, ChunkManifest, ChunkPreview, ChunkingResult
from services import audit_log_service

# Token budget (1 token ≈ 4 chars)
_MIN_TOKENS = 300
_MAX_TOKENS = 900
_PREVIEW_CHARS = 200
_MANIFEST_PREVIEW_COUNT = 5


# ── internal block representation ─────────────────────────────────────────────

@dataclass
class _Block:
    kind: str    # "heading" | "code" | "table" | "text"
    text: str
    level: int = field(default=0)    # 1-6 for headings
    htext: str = field(default="")   # clean heading text


def _tok(text: str) -> int:
    return max(1, len(text) // 4)


# ── block parser ──────────────────────────────────────────────────────────────

def _parse_blocks(markdown: str) -> List[_Block]:
    lines = markdown.split("\n")
    blocks: List[_Block] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Heading
        hm = re.match(r"^(#{1,6})\s+(.*)", line)
        if hm:
            blocks.append(_Block(
                kind="heading",
                text=line,
                level=len(hm.group(1)),
                htext=hm.group(2).strip(),
            ))
            i += 1
            continue

        # Code fence (``` or ~~~)
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = "```" if stripped.startswith("```") else "~~~"
            code_lines = [line]
            i += 1
            while i < n:
                code_lines.append(lines[i])
                # Closing fence: starts with same fence token and not the opening line
                if len(code_lines) > 1 and lines[i].strip().startswith(fence):
                    i += 1
                    break
                i += 1
            blocks.append(_Block(kind="code", text="\n".join(code_lines)))
            continue

        # Markdown table — collect consecutive | lines
        if stripped.startswith("|"):
            table_lines = [line]
            i += 1
            while i < n and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append(_Block(kind="table", text="\n".join(table_lines)))
            continue

        # Paragraph text — collect until blank line or special token
        para: List[str] = [line]
        i += 1
        while i < n:
            l, ls = lines[i], lines[i].strip()
            if not ls:
                i += 1  # consume blank line
                break
            if re.match(r"^#{1,6}\s", l) or ls.startswith("```") or ls.startswith("~~~") or ls.startswith("|"):
                break
            para.append(l)
            i += 1
        text = "\n".join(para).strip()
        if text:
            blocks.append(_Block(kind="text", text=text))

    return blocks


# ── chunk assembly ────────────────────────────────────────────────────────────

def _content_type(pending: List[_Block]) -> str:
    kinds = {b.kind for b in pending if b.kind != "heading"}
    if kinds == {"code"}:
        return "code"
    if kinds == {"table"}:
        return "table"
    return "text"


def _make_chunk(
    pending: List[_Block],
    section_path: List[str],
    document_id: str,
    document_version: str,
    chunk_index: int,
) -> Chunk:
    text = "\n\n".join(b.text for b in pending).strip()
    return Chunk(
        chunk_id=str(uuid.uuid4()),
        document_id=document_id,
        document_version=document_version,
        section_path=section_path[:],
        chunk_index=chunk_index,
        content_type=_content_type(pending),
        text=text,
        char_count=len(text),
        estimated_tokens=_tok(text),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _flush(
    pending: List[_Block],
    section_path: List[str],
    document_id: str,
    document_version: str,
    chunk_index: int,
) -> Tuple[List[Chunk], int]:
    """Flush pending blocks into a chunk. Returns ([chunk], next_index)."""
    if not pending:
        return [], chunk_index
    text = "\n\n".join(b.text for b in pending).strip()
    if not text:
        return [], chunk_index
    return [_make_chunk(pending, section_path, document_id, document_version, chunk_index)], chunk_index + 1


def _chunk_markdown(
    markdown: str,
    document_id: str,
    document_version: str = "1",
) -> List[Chunk]:
    blocks = _parse_blocks(markdown)
    chunks: List[Chunk] = []
    pending: List[_Block] = []
    current_tokens = 0
    heading_stack: List[Tuple[int, str]] = []
    section_path: List[str] = []
    idx = 0

    for block in blocks:
        if block.kind == "heading":
            # Flush whatever we have before this heading
            new, idx = _flush(pending, section_path, document_id, document_version, idx)
            chunks.extend(new)
            pending = []
            current_tokens = 0

            # Update section path
            while heading_stack and heading_stack[-1][0] >= block.level:
                heading_stack.pop()
            heading_stack.append((block.level, block.htext))
            section_path = [t for _, t in heading_stack]

            # Heading starts the new chunk
            pending = [block]
            current_tokens = _tok(block.text)
            continue

        block_tokens = _tok(block.text)

        if block.kind in ("code", "table"):
            # Preserve intact: flush current chunk first if it has enough content
            if pending and current_tokens >= _MIN_TOKENS:
                new, idx = _flush(pending, section_path, document_id, document_version, idx)
                chunks.extend(new)
                pending = []
                current_tokens = 0
            pending.append(block)
            current_tokens += block_tokens
        else:
            # Text: flush if adding would exceed MAX and we already have enough
            if pending and current_tokens + block_tokens > _MAX_TOKENS and current_tokens >= _MIN_TOKENS:
                new, idx = _flush(pending, section_path, document_id, document_version, idx)
                chunks.extend(new)
                pending = []
                current_tokens = 0
            pending.append(block)
            current_tokens += block_tokens

    # Final flush
    new, idx = _flush(pending, section_path, document_id, document_version, idx)
    chunks.extend(new)
    return chunks


# ── service ───────────────────────────────────────────────────────────────────

class ChunkingService:
    def chunk(self, document_id: str) -> ChunkingResult:
        converted_dir = storage_path(settings.converted_dir, document_id)
        out_dir = storage_path(settings.chunks_dir, document_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        markdown = (converted_dir / "document.md").read_text(encoding="utf-8")
        chunks = _chunk_markdown(markdown, document_id)

        # Write chunks.jsonl
        jsonl_path = out_dir / "chunks.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")

        total_tokens = sum(c.estimated_tokens for c in chunks)
        avg_tokens = total_tokens // len(chunks) if chunks else 0
        doc_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()

        manifest = ChunkManifest(
            document_id=document_id,
            total_chunks=len(chunks),
            total_estimated_tokens=total_tokens,
            average_chunk_tokens=avg_tokens,
            created_at=datetime.now(timezone.utc).isoformat(),
            chunking_strategy="heading_aware",
            source_document_md_sha256=doc_sha,
        )
        (out_dir / "chunk_manifest.json").write_text(
            json.dumps(manifest.model_dump(), indent=2)
        )

        audit_log_service.append(
            "chunking",
            document_id,
            chunk_count=len(chunks),
            total_tokens=total_tokens,
            strategy=manifest.chunking_strategy,
        )

        with get_session() as session:
            repository.create_chunk_manifest(
                session,
                document_id=document_id,
                total_chunks=len(chunks),
                total_estimated_tokens=total_tokens,
                chunking_strategy=manifest.chunking_strategy,
                manifest_data=manifest.model_dump(),
            )
            repository.update_document_phase(session, document_id, phase="chunked")

        return ChunkingResult(
            document_id=document_id,
            manifest=manifest,
            chunks_preview=self._previews(chunks[:_MANIFEST_PREVIEW_COUNT]),
        )

    def get_result(self, document_id: str) -> ChunkingResult:
        out_dir = storage_path(settings.chunks_dir, document_id)
        manifest = ChunkManifest(
            **json.loads((out_dir / "chunk_manifest.json").read_text())
        )
        previews: List[ChunkPreview] = []
        with open(out_dir / "chunks.jsonl", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= _MANIFEST_PREVIEW_COUNT:
                    break
                if line.strip():
                    c = json.loads(line)
                    previews.append(ChunkPreview(
                        chunk_id=c["chunk_id"],
                        chunk_index=c["chunk_index"],
                        section_path=c["section_path"],
                        content_type=c["content_type"],
                        text_preview=c["text"][:_PREVIEW_CHARS],
                        char_count=c["char_count"],
                        estimated_tokens=c["estimated_tokens"],
                    ))
        return ChunkingResult(
            document_id=document_id,
            manifest=manifest,
            chunks_preview=previews,
        )

    @staticmethod
    def _previews(chunks: List[Chunk]) -> List[ChunkPreview]:
        return [
            ChunkPreview(
                chunk_id=c.chunk_id,
                chunk_index=c.chunk_index,
                section_path=c.section_path,
                content_type=c.content_type,
                text_preview=c.text[:_PREVIEW_CHARS],
                char_count=c.char_count,
                estimated_tokens=c.estimated_tokens,
            )
            for c in chunks
        ]
