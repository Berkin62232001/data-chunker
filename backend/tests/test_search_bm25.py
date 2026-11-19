import math

import pytest
from pydantic import ValidationError

from core.config import Settings, settings
from models.chunk_models import Chunk
from services.search_service import _bm25_scores, _tokenize
from tests.test_search import full_pipeline, search


def chunk(index, text, section_path=None):
    return Chunk(
        chunk_id=f"chunk-{index}",
        document_id="bm25-test",
        document_version="1",
        section_path=section_path or [],
        chunk_index=index,
        content_type="text",
        text=text,
        char_count=len(text),
        estimated_tokens=max(1, len(text) // 4),
        sha256="a" * 64,
    )


@pytest.mark.parametrize("query, text", [
    ("ÇİFTLİK", "çiftlik"),
    ("IŞIK", "ışık"),
    ("İSTANBUL", "istanbul"),
    ("su\u0308ru\u0308s\u0327", "sürüş"),
    ("ＭＢＺＵＡＩ", "MBZUAI"),
    ("ΚΌΣΜΟΣ", "κόσμος"),
])
def test_search_matches_unicode_through_api(client, query, text):
    document_id = full_pipeline(client, f"# Data\n\n{text} verisi.".encode(), "unicode.md")

    response = search(client, document_id, query, include_full_text=True)

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert text in response.json()["results"][0]["text"]


def test_bm25_weights_rare_terms_over_repeated_common_terms(client):
    markdown = (
        "# General\n\nprogram "
        + "program " * 40
        + "\n\n# Language scores\n\nMBZUAI IELTS TOEFL admission program."
        + "\n\n# Other\n\nAnother program."
    )
    document_id = full_pipeline(client, markdown.encode(), "rare.md")

    response = search(client, document_id, "MBZUAI IELTS TOEFL program")

    assert response.status_code == 200
    assert response.json()["results"][0]["section_path"] == ["Language scores"]


def test_bm25_matches_single_document_formula():
    scores = _bm25_scores(["alpha"], [chunk(0, "alpha beta")])

    assert scores == pytest.approx([math.log1p(0.5 / 1.5)])


def test_bm25_deduplicates_query_terms():
    chunks = [chunk(0, "alpha beta"), chunk(1, "beta gamma")]

    assert _bm25_scores(["alpha", "beta", "alpha"], chunks) == _bm25_scores(["alpha", "beta"], chunks)


def test_bm25_keeps_metadata_heading_matches_and_weight_setting(monkeypatch):
    chunks = [chunk(0, "hello world", ["Quantum"]), chunk(1, "quantum world")]
    boosted = _bm25_scores(["quantum"], chunks)
    assert boosted[0] > boosted[1] > 0

    monkeypatch.setattr(settings, "keyword_section_weight", 0)
    unboosted = _bm25_scores(["quantum"], chunks)
    assert unboosted[0] == 0
    assert unboosted[1] > 0


def test_bm25_saturates_term_frequency(monkeypatch):
    monkeypatch.setattr(settings, "keyword_bm25_b", 0)
    scores = _bm25_scores(["alpha"], [chunk(0, "alpha"), chunk(1, "alpha " * 30)])

    assert scores[0] < scores[1] < scores[0] * (settings.keyword_bm25_k1 + 1)


def test_bm25_normalizes_document_lengths():
    scores = _bm25_scores(["alpha"], [chunk(0, "alpha beta"), chunk(1, "alpha " + "beta " * 50)])

    assert scores[0] > scores[1] > 0


def test_bm25_handles_empty_and_tokenless_chunks(monkeypatch):
    monkeypatch.setattr(settings, "keyword_bm25_b", 1)
    chunks = [chunk(0, ""), chunk(1, "!!!", ["Alpha"])]

    assert _bm25_scores(["alpha"], []) == []
    assert _bm25_scores([], chunks) == [0, 0]
    scores = _bm25_scores(["alpha"], chunks)
    assert scores[0] == 0
    assert math.isfinite(scores[1]) and scores[1] > 0
    assert _tokenize("!? _") == []


def test_search_returns_stable_ties_and_ignores_punctuation_queries(client):
    document_id = full_pipeline(client, ("# Same\n\nIdentical content.\n\n" * 4).encode(), "ties.md")

    results = search(client, document_id, "identical", top_k=3).json()["results"]

    assert [item["chunk_index"] for item in results] == [0, 1, 2]
    assert len({item["score"] for item in results}) == 1
    assert search(client, document_id, "!? _").json()["results"] == []
    assert search(client, document_id, "ident").json()["results"] == []


@pytest.mark.parametrize("field, value", [
    ("keyword_bm25_k1", 0),
    ("keyword_bm25_k1", float("nan")),
    ("keyword_bm25_k1", float("inf")),
    ("keyword_bm25_b", -0.1),
    ("keyword_bm25_b", 1.1),
    ("keyword_section_weight", -1),
])
def test_bm25_settings_reject_invalid_parameters(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
