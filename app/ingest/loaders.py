"""Multi-format intake: Markdown, HTML, plain text and PDF → plain text with source identity.

Vendor / product / version come from the folder layout
``<corpus>/<vendor>/<product>/<version>/<file>``; title, doc_type and url come from
front matter (md/txt), <meta> tags (html) or a ``<file>.meta.yaml`` sidecar (pdf).
Every loader returns text in a light Markdown form (``#`` headings) so the chunker can
find section boundaries regardless of the original format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".html", ".htm", ".txt", ".pdf"}
DOC_TYPES = {"runbook", "config_guide", "vendor_manual", "release_notes"}

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TXT_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][^\n]{0,80})$")


@dataclass
class Document:
    doc_id: str
    text: str
    vendor: str
    product: str
    version: str
    doc_type: str
    title: str
    url: str
    source_path: str
    format: str
    line_offset: int = 0  # lines stripped before `text` (front matter), so citations match the source file
    extra: dict = field(default_factory=dict)

    def metadata(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "vendor": self.vendor,
            "product": self.product,
            "version": self.version,
            "doc_type": self.doc_type,
            "title": self.title,
            "url": self.url,
            "source_path": self.source_path,
            "format": self.format,
        }


class DocumentLoadError(ValueError):
    pass


def infer_doc_type(filename: str) -> str:
    name = filename.lower()
    if "runbook" in name or "troubleshoot" in name:
        return "runbook"
    if "release" in name or "changelog" in name:
        return "release_notes"
    if "config" in name:
        return "config_guide"
    return "vendor_manual"


def split_front_matter(raw: str) -> tuple[dict, str]:
    match = _FRONT_MATTER.match(raw)
    if not match:
        return {}, raw
    meta = yaml.safe_load(match.group(1)) or {}
    meta["_line_offset"] = match.group(0).count("\n")
    return meta, raw[match.end():]


def _load_markdown(path: Path) -> tuple[dict, str]:
    return split_front_matter(path.read_text(encoding="utf-8", errors="replace"))


def _load_text(path: Path) -> tuple[dict, str]:
    meta, body = split_front_matter(path.read_text(encoding="utf-8", errors="replace"))
    lines = []
    for line in body.splitlines():
        m = _TXT_HEADING.match(line.strip()) if not line.startswith((" ", "\t")) else None
        lines.append(f"## {m.group(1)}. {m.group(2)}" if m else line)
    return meta, "\n".join(lines)


def _load_html(path: Path) -> tuple[dict, str]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    meta: dict = {}
    if soup.title and soup.title.string:
        meta["title"] = soup.title.string.strip()
    for tag in soup.find_all("meta"):
        name, content = tag.get("name"), tag.get("content")
        if name in {"doc_type", "url", "title"} and content:
            meta[name] = content.strip()

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    root = soup.find("main") or soup.body or soup

    parts: list[str] = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "td"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in {"h1", "h2", "h3", "h4"}:
            parts.append(f"\n{'#' * int(el.name[1])} {text}\n")
        elif el.name == "li":
            parts.append(f"- {text}")
        else:
            parts.append(text + "\n")
    return meta, "\n".join(parts)


def _load_pdf(path: Path) -> tuple[dict, str]:
    from pypdf import PdfReader

    sidecar = path.with_name(path.name + ".meta.yaml")
    meta = yaml.safe_load(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    reader = PdfReader(str(path))
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"## Page {number}\n\n{text}")
    return meta or {}, "\n\n".join(pages)


_LOADERS = {
    ".md": _load_markdown,
    ".markdown": _load_markdown,
    ".txt": _load_text,
    ".html": _load_html,
    ".htm": _load_html,
    ".pdf": _load_pdf,
}


def load_document(path: Path, corpus_dir: Path) -> Document:
    rel = path.relative_to(corpus_dir)
    if len(rel.parts) != 4:
        raise DocumentLoadError(
            f"{rel.as_posix()}: expected <vendor>/<product>/<version>/<file>, got {len(rel.parts)} path parts"
        )
    vendor, product, version, filename = rel.parts
    ext = path.suffix.lower()
    meta, text = _LOADERS[ext](path)

    doc_type = str(meta.get("doc_type") or infer_doc_type(filename))
    if doc_type not in DOC_TYPES:
        raise DocumentLoadError(f"{rel.as_posix()}: unknown doc_type '{doc_type}'")

    title = str(meta.get("title") or path.stem.replace("-", " ").title())
    return Document(
        doc_id=rel.as_posix(),
        text=text,
        vendor=vendor,
        product=product,
        version=str(version),
        doc_type=doc_type,
        title=title,
        url=str(meta.get("url", "")),
        source_path=rel.as_posix(),
        format=ext.lstrip("."),
        line_offset=int(meta.get("_line_offset", 0)),
    )


def discover_files(corpus_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in corpus_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and p.name.lower() != "readme.md"
    )


def load_corpus(corpus_dir: Path) -> tuple[list[Document], list[str]]:
    """Load every supported file. Returns (documents, errors) — errors do not stop the run."""
    documents, errors = [], []
    for path in discover_files(corpus_dir):
        try:
            documents.append(load_document(path, corpus_dir))
        except Exception as exc:  # noqa: BLE001 — report and keep going
            errors.append(f"{path}: {exc}")
    return documents, errors
