import pytest

from app.rag import build_context
from app.tokens import estimate_tokens
from app.vectorstore import RetrievedChunk


def chunk(text):
    return RetrievedChunk("id", text, 1.0, dict(title="T", product="P", version="1",
                                              section="S", line_start=1, line_end=2))


@pytest.mark.parametrize("budget", [0, 1, 20, 151, 160, 200, 400])
def test_context_respects_budget_with_long_unbroken_excerpt(budget):
    context, used = build_context([chunk("x" * 5000)], budget)
    assert estimate_tokens(context) <= budget
    assert bool(context) == bool(used)


def test_separators_count_toward_context_budget():
    chunks = [chunk("abcd" * 10) for _ in range(3)]
    single, _ = build_context(chunks[:1], 100)
    # The old implementation fits three blocks but forgets both separators.
    budget = estimate_tokens(single) * 3
    context, used = build_context(chunks, budget)
    assert estimate_tokens(context) <= budget
    assert len(used) == 2
