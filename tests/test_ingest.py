from pathlib import Path

import pytest

from app.config import ROOT_DIR
from app.ingest.chunking import chunk_document
from app.ingest.cleaning import clean_text
from app.ingest.loaders import Document, DocumentLoadError, infer_doc_type, load_corpus, load_document

CORPUS = ROOT_DIR / "data" / "corpus"


def test_clean_text_strips_boilerplate_and_keeps_line_count():
    raw = "Home | Products | Docs\nReal   content\x07 here\r\nCookie settings — Sign in\n​next"
    cleaned = clean_text(raw)
    assert cleaned.split("\n") == ["", "Real content here", "", "next"]


def test_markdown_front_matter_and_folder_metadata():
    doc = load_document(CORPUS / "aurora-networks/AX-9000/8.1/troubleshooting-runbook.md", CORPUS)
    assert (doc.vendor, doc.product, doc.version, doc.doc_type) == ("aurora-networks", "AX-9000", "8.1", "runbook")
    assert doc.title == "AX-9000 Troubleshooting Runbook"
    assert doc.url.startswith("https://")
    assert doc.line_offset == 6  # 5 front-matter lines + the blank line after it
    assert not doc.text.startswith("---")


def test_html_loader_removes_navigation_and_reads_meta():
    doc = load_document(CORPUS / "aurora-networks/AX-9000/7.4/alarm-reference-manual.html", CORPUS)
    assert doc.doc_type == "vendor_manual"
    assert "## AX-ALM-5001 Power supply failure" in doc.text
    assert "Support portal" not in doc.text and "Privacy" not in doc.text


def test_txt_loader_turns_numbered_titles_into_headings():
    doc = load_document(CORPUS / "helix-radio/HX-5G-gNB/22.3/operations-manual.txt", CORPUS)
    assert "## 2. Cell administration" in doc.text
    assert "hxcli cell lock --cell-id <id>" in doc.text


def test_bad_layout_is_rejected(tmp_path):
    bad = tmp_path / "vendor" / "doc.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("# x", encoding="utf-8")
    with pytest.raises(DocumentLoadError):
        load_document(bad, tmp_path)


@pytest.mark.parametrize("name,expected", [
    ("troubleshooting-runbook.md", "runbook"),
    ("release-notes.md", "release_notes"),
    ("configuration-guide.md", "config_guide"),
    ("alarm-manual.pdf", "vendor_manual"),
])
def test_infer_doc_type(name, expected):
    assert infer_doc_type(name) == expected


def test_whole_corpus_loads_without_errors():
    documents, errors = load_corpus(CORPUS)
    assert errors == []
    assert len(documents) >= 10
    assert {d.version for d in documents} >= {"7.4", "8.1", "22.3", "23.1"}


def _doc(text: str) -> Document:
    return Document(doc_id="v/p/1.0/x.md", text=text, vendor="v", product="p", version="1.0",
                    doc_type="runbook", title="X", url="", source_path="v/p/1.0/x.md", format="md")


def test_chunks_respect_size_and_keep_procedures_whole():
    documents, _ = load_corpus(CORPUS)
    for doc in documents:
        doc.text = clean_text(doc.text)
        for chunk in chunk_document(doc, max_tokens=350, overlap_tokens=50):
            assert chunk.token_count <= 385, chunk.chunk_id
            assert chunk.section
            assert chunk.metadata()["version"] == doc.version

    runbook = next(d for d in documents if d.doc_id.endswith("22.3/troubleshooting-runbook.md"))
    sections = [c.section for c in chunk_document(runbook, 350, 50)]
    assert "RN-203 NG-C link to AMF down" in sections  # whole procedure in one chunk


def test_chunk_line_numbers_point_into_the_source_file():
    path = CORPUS / "aurora-networks/AX-9000/7.4/troubleshooting-runbook.md"
    doc = load_document(path, CORPUS)
    doc.text = clean_text(doc.text)
    source_lines = path.read_text(encoding="utf-8").split("\n")
    for chunk in chunk_document(doc, 350, 50):
        first_line = chunk.text.split("\n")[0]
        assert source_lines[chunk.line_start - 1].strip() == first_line.strip()


def test_long_sections_split_with_overlap():
    body = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(8))
    chunks = chunk_document(_doc(f"# Title\n\n## Long section\n\n{body}"), max_tokens=120, overlap_tokens=80)
    assert len(chunks) > 2
    assert all(c.section == "Long section" for c in chunks)
    # consecutive windows share their boundary paragraph
    first_tail = chunks[0].text.split("\n\n")[-1]
    assert first_tail in chunks[1].text
