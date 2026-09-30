import pytest
from app.tokens import estimate_tokens, trim_to_tokens


@pytest.mark.parametrize("budget", [0, 1, 2, 10])
@pytest.mark.parametrize("text", ["x" * 100, "word " * 30])
def test_truncation_includes_ellipsis_in_budget(text, budget):
    assert estimate_tokens(trim_to_tokens(text, budget)) <= budget


def test_text_that_fits_is_unchanged():
    assert trim_to_tokens("abcd", 1) == "abcd"
