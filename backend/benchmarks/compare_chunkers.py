"""Compare PDF pipelines using frozen questions, shared BM25 and a context budget.

Run from the repository root:
    backend/.venv/bin/python backend/benchmarks/compare_chunkers.py \
        --pdf-dir /path/to/pdfs --output /tmp/chunker-comparison.json

Optional competitor dependencies require Python 3.10+:
    docling docling-core[chunking-openai] unstructured[pdf] tiktoken

The default chars4 counter is an estimate. Select --tokenizer cl100k_base for
model token counts. Missing dependencies produce explicit blocked results.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


def supports_answer(question, chunks):
    if question["expected_answer"] is None:
        return False
    reference_pages = set(question["source_pages"])
    texts = [
        chunk["text"] for chunk in chunks
        if not chunk["pages"] or reference_pages.intersection(chunk["pages"])
    ]
    normalized = unicodedata.normalize("NFKC", "\n".join(texts)).casefold()
    normalized = re.sub(r"\s+", " ", normalized.replace("\u0307", ""))
    return all(re.search(pattern, normalized) for pattern in question["patterns"])


def token_counter(name):
    if name == "chars4":
        return lambda text: (len(text) + 3) // 4
    import tiktoken
    encoding = tiktoken.get_encoding(name)
    return lambda text: len(encoding.encode(text, disallowed_special=()))


def context_text(chunks):
    return "\n\n".join(f"[C{i}]\n{chunk['text']}" for i, chunk in enumerate(chunks, 1))


def select_context(ranked, count_tokens, budget, max_chunks):
    selected = []
    for chunk in ranked:
        if len(selected) == max_chunks:
            break
        candidate = selected + [chunk]
        if count_tokens(context_text(candidate)) <= budget:
            selected.append(chunk)
    return selected


def evaluate_questions(chunks, questions, count_tokens, budget, top_k):
    from models.chunk_models import Chunk
    from services.search_service import _bm25_scores, _tokenize

    # Use text-only inputs so every pipeline receives the same BM25 scoring.
    models = [
        Chunk(
            chunk_id=str(i), document_id="benchmark", document_version="1",
            section_path=[], chunk_index=i, content_type="text", text=chunk["text"],
            char_count=len(chunk["text"]), estimated_tokens=max(1, count_tokens(chunk["text"])),
            sha256=hashlib.sha256(chunk["text"].encode()).hexdigest(),
        )
        for i, chunk in enumerate(chunks)
    ]
    results = []
    for question in questions:
        started = time.perf_counter()
        scores = _bm25_scores(_tokenize(question["question"]), models)
        ranked_indices = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
        ranked = [dict(chunks[i], index=i) for i in ranked_indices if scores[i] > 0]
        selected = select_context(ranked, count_tokens, budget, top_k)
        context_tokens = count_tokens(context_text(selected))
        assert context_tokens <= budget
        retrieval_ms = round((time.perf_counter() - started) * 1000, 3)
        first_support_rank = next(
            (i for i in range(1, len(ranked) + 1) if supports_answer(question, ranked[:i])),
            None,
        )
        off_reference_tokens = None
        if question["expected_answer"] is not None and selected and all(c["pages"] for c in selected):
            off_reference_tokens = sum(
                count_tokens(c["text"]) for c in selected
                if not set(c["pages"]).intersection(question["source_pages"])
            )
        results.append({
            **question,
            "first_support_rank": first_support_rank,
            "hit_at_1": supports_answer(question, ranked[:1]),
            "hit_at_3": supports_answer(question, ranked[:3]),
            "budget_hit": supports_answer(question, selected),
            "source_fact_preserved": supports_answer(question, chunks),
            "selected_indices": [c["index"] for c in selected],
            "selected_pages": [c["pages"] for c in selected],
            "context_tokens": context_tokens,
            "returned_chunks": len(ranked),
            "off_reference_page_chunk_tokens": off_reference_tokens,
            "retrieval_ms": retrieval_ms,
        })
    answerable = [q for q in results if q["expected_answer"] is not None]
    negatives = [q for q in results if q["expected_answer"] is None]
    matched = [q for q in answerable if q["budget_hit"]]
    return {
        "answerable_questions": len(answerable),
        "hit_at_1": sum(q["hit_at_1"] for q in answerable),
        "hit_at_3": sum(q["hit_at_3"] for q in answerable),
        "hit_within_budget": sum(q["budget_hit"] for q in answerable),
        "preserved_reference_facts": sum(q["source_fact_preserved"] for q in answerable),
        "negative_questions_returning_chunks": sum(q["returned_chunks"] > 0 for q in negatives),
        "median_context_tokens_on_hits": statistics.median([q["context_tokens"] for q in matched]) if matched else None,
        "queries": results,
    }


def export_chunks(method, pdf):
    started = time.perf_counter()
    if method == "project":
        from services.converters.pdf import PdfConverter
        from services.chunking_service import _chunk_markdown

        # Pin the actual project profile tested before optional Docling installation.
        conversion = PdfConverter()._convert_with_pypdf(pdf)
        if conversion.errors:
            raise RuntimeError("; ".join(conversion.errors))
        converted_at = time.perf_counter()
        chunks = []
        for item in _chunk_markdown(conversion.markdown, "benchmark"):
            pages = [int(match.group(1)) for heading in item.section_path
                     if (match := re.fullmatch(r"Page (\d+)", heading))]
            chunks.append({"text": item.text, "pages": pages})
        profile = "pypdf_fallback + heading_aware"
    elif method == "docling":
        import tiktoken
        from docling.chunking import HybridChunker
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer

        options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
        options.accelerator_options = AcceleratorOptions(
            device=AcceleratorDevice.CPU, num_threads=4,
        )
        converter = DocumentConverter(format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        })
        document = converter.convert(pdf).document
        converted_at = time.perf_counter()
        tokenizer = OpenAITokenizer(tokenizer=tiktoken.get_encoding("cl100k_base"), max_tokens=900)
        chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)
        chunks = [
            {
                "text": chunker.contextualize(item),
                "pages": sorted({p.page_no for doc_item in item.meta.doc_items for p in doc_item.prov}),
            }
            for item in chunker.chunk(dl_doc=document)
        ]
        profile = "CPU PDF table extraction, OCR off + HybridChunker/cl100k_base/900"
    else:
        from unstructured.chunking.title import chunk_by_title
        from unstructured.partition.pdf import partition_pdf

        strategy = "fast" if method == "unstructured_fast" else "hi_res"
        elements = partition_pdf(
            filename=str(pdf), strategy=strategy, infer_table_structure=strategy == "hi_res",
        )
        converted_at = time.perf_counter()
        chunks = []
        for item in chunk_by_title(
            elements, max_characters=3600, new_after_n_chars=3200,
            combine_text_under_n_chars=1200, multipage_sections=False,
            include_orig_elements=True,
        ):
            originals = item.metadata.orig_elements or [item]
            pages = sorted({e.metadata.page_number for e in originals if e.metadata.page_number})
            chunks.append({"text": item.text, "pages": pages})
        profile = f"{strategy} PDF extraction + by_title/3600 characters"
    completed = time.perf_counter()
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_mib = peak_rss / (1024 * 1024 if sys.platform == "darwin" else 1024)
    return {
        "status": "ok", "profile": profile, "chunks": chunks,
        "conversion_seconds": round(converted_at - started, 4),
        "chunking_seconds": round(completed - converted_at, 4),
        "worker_peak_rss_mib": round(peak_rss_mib, 2),
    }


def worker(args):
    try:
        result = export_chunks(args.worker, args.pdf)
    except (ImportError, ModuleNotFoundError) as exc:
        result = {"status": "blocked", "error": str(exc)}
    except Exception as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    args.output.write_text(json.dumps(result, ensure_ascii=False))


def measure_pipeline(method, pdf, repeats, timeout):
    attempts = []
    with tempfile.TemporaryDirectory(prefix="chunker-worker-") as directory:
        result_path = Path(directory) / "result.json"
        for attempt in range(repeats):
            result_path.unlink(missing_ok=True)
            started = time.perf_counter()
            try:
                process = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--worker", method,
                     "--pdf", str(pdf), "--output", str(result_path)],
                    capture_output=True, text=True, timeout=timeout,
                    env={
                        **os.environ,
                        "CUDA_VISIBLE_DEVICES": "",
                        "OMP_NUM_THREADS": "4",
                        "MKL_NUM_THREADS": "4",
                        "OPENBLAS_NUM_THREADS": "4",
                    },
                )
            except subprocess.TimeoutExpired:
                return {"status": "error", "error": f"Worker exceeded {timeout} seconds."}
            if not result_path.exists():
                return {"status": "error", "error": process.stderr[-1500:]}
            result = json.loads(result_path.read_text())
            if result["status"] != "ok":
                return result
            attempts.append({
                "run": attempt + 1, "process_wall_seconds": round(time.perf_counter() - started, 4),
                "conversion_seconds": result["conversion_seconds"],
                "chunking_seconds": result["chunking_seconds"],
                "peak_rss_mib": result["worker_peak_rss_mib"],
            })
        result["runs"] = attempts
        result["median_process_wall_seconds"] = statistics.median(r["process_wall_seconds"] for r in attempts)
        result["median_peak_rss_mib"] = statistics.median(r["peak_rss_mib"] for r in attempts)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path(__file__).with_name("pdf_questions.json"))
    parser.add_argument("--pdf-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--methods", nargs="+", choices=["project", "docling", "unstructured", "unstructured_fast"],
                        default=["project", "docling", "unstructured"])
    parser.add_argument("--budget", type=int, default=2000)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--tokenizer", choices=["chars4", "cl100k_base"], default="chars4")
    parser.add_argument("--worker", choices=["project", "docling", "unstructured", "unstructured_fast"], help=argparse.SUPPRESS)
    parser.add_argument("--pdf", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return 0
    if args.pdf_dir is None:
        parser.error("--pdf-dir is required")
    if min(args.budget, args.top_k, args.repeats, args.timeout) < 1:
        parser.error("--budget, --top-k, --repeats and --timeout must be positive")
    if args.output.exists():
        parser.error("Choose a new output path for each run.")
    if not args.suite.is_file():
        parser.error("Private question suites are excluded from Git. Supply your own JSON file with --suite.")
    count_tokens = token_counter(args.tokenizer)
    suite = json.loads(args.suite.read_text())
    report = {
        "python": sys.version, "platform": platform.platform(),
        "suite_sha256": hashlib.sha256(args.suite.read_bytes()).hexdigest(),
        "retrieval": "shared project Unicode BM25, metadata boost disabled",
        "tokenizer": args.tokenizer, "context_budget": args.budget,
        "max_selected_chunks": args.top_k,
        "measurement_notes": [
            "chars4 counts ceil(characters/4), including citation labels and separators.",
            "Each run starts a fresh process; model initialization is included.",
            "First-run downloads can affect timing. No claim of warm-model latency.",
            "Fact preservation covers only the annotated answer facts.",
            "Off-reference-page tokens are a coarse noise proxy, not semantic precision.",
            "Negative-question retrieval does not measure final-answer abstention.",
        ],
        "packages": {}, "documents": [],
    }
    for package in ("pypdf", "docling", "docling-core", "unstructured", "tiktoken"):
        try:
            report["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["packages"][package] = None
    for document in suite["documents"]:
        pdf = args.pdf_dir / document["filename"]
        document_result = {"filename": document["filename"], "methods": {}}
        if not pdf.is_file():
            document_result["status"] = "missing_pdf"
            report["documents"].append(document_result)
            continue
        document_result["pdf_sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        for method in args.methods:
            print(f"{document['filename']} / {method}", flush=True)
            result = measure_pipeline(method, pdf.resolve(), args.repeats, args.timeout)
            if result["status"] == "ok":
                result["evaluation"] = evaluate_questions(
                    result["chunks"], document["questions"], count_tokens, args.budget, args.top_k,
                )
                texts = [c["text"] for c in result["chunks"]]
                result["chunk_count"] = len(texts)
                result["separator_only_chunks"] = sum(
                    bool(re.fullmatch(r"[\s*_\-=]+", text)) for text in texts
                )
                result["chunks_over_900_counter_tokens"] = sum(count_tokens(t) > 900 for t in texts)
            document_result["methods"][method] = result
            print(f"  {result['status']}", flush=True)
        report["documents"].append(document_result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return int(any(
        document.get("status") == "missing_pdf"
        or any(method["status"] != "ok" for method in document["methods"].values())
        for document in report["documents"]
    ))


if __name__ == "__main__":
    raise SystemExit(main())
