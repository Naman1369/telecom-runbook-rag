import pytest
from app.rag import detect_release


@pytest.mark.parametrize("question", ["release 8.1.2", "release 8.1beta", "asset8.1", "18.1"])
def test_does_not_infer_a_different_release_from_prefix(question):
    catalog = {"products": [{"product": "Router", "versions": [{"version": "8.1"}]}]}
    assert detect_release(question, catalog) is None


@pytest.mark.parametrize("question", ["release 8.1.", "on (8.1)", "release 8.1 failed"])
def test_release_followed_by_punctuation_is_detected(question):
    catalog = {"products": [{"product": "Router", "versions": [{"version": "8.1"}]}]}
    assert detect_release(question, catalog) == ("Router", "8.1")


@pytest.mark.parametrize("question", ["router on v8.1 is down", "running R8.1", "(V8.1)"])
def test_release_with_v_or_r_prefix_is_detected(question):
    catalog = {"products": [{"product": "Router", "versions": [{"version": "8.1"}]}]}
    assert detect_release(question, catalog) == ("Router", "8.1")


@pytest.mark.parametrize("question", ["server8.1", "rev8.1", "xv8.1"])
def test_prefix_inside_a_word_is_not_a_release(question):
    catalog = {"products": [{"product": "Router", "versions": [{"version": "8.1"}]}]}
    assert detect_release(question, catalog) is None
