from benchmarks.compare_chunkers import (
    context_text,
    evaluate_questions,
    select_context,
    supports_answer,
    token_counter,
)


def question(expected_answer="fact"):
    return {
        "id": "Q1",
        "category": "test",
        "question": "uniquefact",
        "expected_answer": expected_answer,
        "source_pages": [1],
        "patterns": ["uniquefact"],
    }


def test_context_budget_counts_labels_and_skips_oversized_chunks():
    count = token_counter("chars4")
    ranked = [
        {"text": "a" * 80, "pages": [1]},
        {"text": "answer", "pages": [2]},
        {"text": "b" * 80, "pages": [3]},
    ]

    selected = select_context(ranked, count, budget=20, max_chunks=3)

    assert selected == [ranked[1]]
    assert count(context_text(selected)) <= 20
    assert count(context_text([ranked[0]])) > 20


def test_context_chunk_limit_is_independent_of_token_budget():
    ranked = [{"text": "answer", "pages": [1]}] * 5

    selected = select_context(ranked, token_counter("chars4"), budget=1000, max_chunks=3)

    assert len(selected) == 3


def test_support_requires_reference_pages_and_all_answer_patterns():
    reference = question()
    reference["patterns"] = ["uniquefact", "support"]

    assert not supports_answer(reference, [{"text": "uniquefact support", "pages": [2]}])
    assert not supports_answer(reference, [{"text": "uniquefact", "pages": [1]}])
    assert supports_answer(reference, [{"text": "uniquefact\nsupport", "pages": [1]}])
    assert not supports_answer(question(None), [{"text": "uniquefact", "pages": [1]}])


def test_circuit_sharing_answer_does_not_require_unrelated_ocr_words():
    reference = question("Resources are not shared.")
    reference["source_pages"] = [16]
    reference["patterns"] = [r"circuit\s+switching", r"no\s+sharing"]
    chunks = [{
        "text": 'Network Core: Circuit Switching. Resource piece /d/e (no sharing).',
        "pages": [16],
    }]

    assert supports_answer(reference, chunks)
    assert not supports_answer(reference, [{"text": "Circuit switching.", "pages": [16]}])


def test_budget_failure_is_distinct_from_retrieval_success():
    chunks = [{"text": "uniquefact " + "background " * 50, "pages": [1]}]

    result = evaluate_questions(chunks, [question()], token_counter("chars4"), budget=10, top_k=3)

    assert result["hit_at_1"] == 1
    assert result["hit_at_3"] == 1
    assert result["hit_within_budget"] == 0
    assert result["preserved_reference_facts"] == 1
    assert result["median_context_tokens_on_hits"] is None


def test_negative_retrieval_is_reported_separately():
    chunks = [{"text": "uniquefact", "pages": [1]}]

    result = evaluate_questions(chunks, [question(None)], token_counter("chars4"), budget=100, top_k=3)

    assert result["answerable_questions"] == 0
    assert result["hit_at_1"] == 0
    assert result["negative_questions_returning_chunks"] == 1


def test_benchmark_reports_off_reference_context_without_claiming_semantic_precision():
    chunks = [
        {"text": "uniquefact", "pages": [1]},
        {"text": "uniquefact context", "pages": [2]},
    ]

    result = evaluate_questions(chunks, [question()], token_counter("chars4"), budget=100, top_k=3)

    assert result["queries"][0]["off_reference_page_chunk_tokens"] > 0
    assert result["hit_within_budget"] == 1
