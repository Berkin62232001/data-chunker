import re
from dataclasses import dataclass
from typing import List

_EXCERPT_CHARS = 200

# Case-insensitive patterns that suggest prompt-injection attempts in document text
_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore (?:previous|all|the|your) instructions?",
        r"forget (?:previous|all|the|your|everything)",
        r"disregard (?:previous|all|the|your) instructions?",
        r"you are (?:now|actually) (?:a|an) ",
        r"new (?:role|persona|instructions?|system prompt)",
        r"act as (?:a|an|if)",
        r"pretend (?:you are|to be)",
        r"override (?:previous|your) instructions?",
        r"\bsystem\s+prompt\b",
        r"\bjailbreak\b",
        r"\bdo anything now\b",
        r"\bdan mode\b",
        r"from now on[,\s]+you",
    ]
]


@dataclass
class InjectionHit:
    chunk_id: str
    chunk_index: int
    matched_pattern: str
    text_excerpt: str


def scan_text(text: str) -> List[str]:
    """Return readable descriptions of any injection patterns found in text."""
    found: List[str] = []
    for pat in _PATTERNS:
        if pat.search(text):
            found.append(pat.pattern)
    return found


def scan_chunks(chunks: list) -> List[InjectionHit]:
    """
    Scan a list of Chunk objects and return one InjectionHit per suspicious chunk.
    Chunks are not modified — callers decide what to do with the warnings.
    """
    hits: List[InjectionHit] = []
    for chunk in chunks:
        matched = scan_text(chunk.text)
        if matched:
            hits.append(InjectionHit(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                matched_pattern=matched[0],
                text_excerpt=chunk.text[:_EXCERPT_CHARS],
            ))
    return hits
