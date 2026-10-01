import pytest
from app.ingest.chunking import chunk_document
from app.ingest.loaders import Document


@pytest.mark.parametrize("maximum,overlap", [(0, 0), (-1, 0), (10, -1), (10, 10), (10, 11)])
def test_invalid_chunk_settings_raise_clear_error(maximum, overlap):
    doc = Document("id", "short", "v", "p", "1", "runbook", "T", "", "x.md", "md")
    with pytest.raises(ValueError, match="tokens"):
        chunk_document(doc, maximum, overlap)


def test_zero_overlap_is_valid():
    doc = Document("id", "short", "v", "p", "1", "runbook", "T", "", "x.md", "md")
    assert chunk_document(doc, 10, 0)[0].text == "short"
