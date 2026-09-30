import pytest
from app.rag import QueryError, QueryRequest, resolve_release


CATALOG = {"products": [
    {"vendor": "A", "product": "Router", "versions": [{"version": "1"}]},
    {"vendor": "B", "product": "Router", "versions": [{"version": "1"}]},
]}


def test_ambiguous_vendor_does_not_select_first_catalog_entry():
    with pytest.raises(QueryError, match="unique"):
        resolve_release(QueryRequest("help", product="Router", version="1"), CATALOG)


def test_explicit_vendor_is_honored():
    assert resolve_release(QueryRequest("help", product="Router", version="1", vendor="B"), CATALOG) == (
        "B", "Router", "1", False
    )


def test_unknown_vendor_does_not_fall_back_to_another_vendor():
    with pytest.raises(QueryError):
        resolve_release(QueryRequest("help", version="1", vendor="unknown"), CATALOG)
