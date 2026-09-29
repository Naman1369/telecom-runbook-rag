"""Section-aware, token-aware chunking with overlap and citation metadata.

Strategy (chosen after comparing fixed-size, paragraph and section-aware splitting — see
docs/CHUNKING.md): runbooks are organised as headed procedures, and an engineer needs the
whole procedure, not half a list. So we

1. build a heading tree from the Markdown-normalised text;
2. keep a heading's whole subtree as one chunk when it fits in ``max_tokens``;
3. otherwise recurse into sub-headings, and split any over-long body greedily on
   paragraph → line boundaries with ``overlap_tokens`` of trailing context carried over.

Every chunk records its heading path and 1-based line range so answers can cite the exact
section and position in the source document.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.ingest.loaders import Document
from app.tokens import CHARS_PER_TOKEN, estimate_tokens

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BLANK_RUNS = re.compile(r"\n\s*\n+")
# A body shorter than this is merged into the first child chunk instead of standing alone.
_MIN_STANDALONE_TOKENS = 40


@dataclass
class Chunk:
    chunk_id: str
    text: str
    embed_text: str
    section: str
    chunk_index: int
    line_start: int
    line_end: int
    token_count: int
    content_hash: str
    doc: Document

    def metadata(self) -> dict:
        meta = self.doc.metadata()
        meta.update(
            chunk_id=self.chunk_id,
            section=self.section,
            chunk_index=self.chunk_index,
            line_start=self.line_start,
            line_end=self.line_end,
            token_count=self.token_count,
            content_hash=self.content_hash,
        )
        return meta


@dataclass
class _Node:
    level: int
    title: str
    body: list[tuple[int, str]] = field(default_factory=list)  # (line_no, text)
    children: list["_Node"] = field(default_factory=list)
    heading_line: int | None = None

    def all_lines(self) -> list[tuple[int, str]]:
        lines = []
        if self.heading_line is not None:
            lines.append((self.heading_line, f"{'#' * self.level} {self.title}"))
        lines.extend(self.body)
        for child in self.children:
            lines.extend(child.all_lines())
        return lines


def _parse_tree(text: str) -> _Node:
    root = _Node(level=0, title="")
    stack = [root]
    for line_no, line in enumerate(text.split("\n"), start=1):
        match = _HEADING.match(line)
        if match:
            level = len(match.group(1))
            while stack[-1].level >= level:
                stack.pop()
            node = _Node(level=level, title=match.group(2), heading_line=line_no)
            stack[-1].children.append(node)
            stack.append(node)
        else:
            stack[-1].body.append((line_no, line))
    return root


def _tokens(lines: list[tuple[int, str]]) -> int:
    return estimate_tokens("\n".join(t for _, t in lines))


def _strip_blank_edges(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    start, end = 0, len(lines)
    while start < end and not lines[start][1].strip():
        start += 1
    while end > start and not lines[end - 1][1].strip():
        end -= 1
    return lines[start:end]


def _units(lines: list[tuple[int, str]], max_tokens: int) -> list[list[tuple[int, str]]]:
    """Split lines into packing units: paragraphs, or single lines for over-long paragraphs."""
    paragraphs, current = [], []
    for item in lines:
        if item[1].strip():
            current.append(item)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)

    units = []
    max_chars = max_tokens * CHARS_PER_TOKEN
    for para in paragraphs:
        if _tokens(para) <= max_tokens:
            units.append(para)
            continue
        for line_no, text in para:
            for start in range(0, len(text), max_chars):
                units.append([(line_no, text[start:start + max_chars])])
    return units


def _pack(lines: list[tuple[int, str]], max_tokens: int, overlap_tokens: int) -> list[list[tuple[int, str]]]:
    units = _units(lines, max_tokens)
    windows: list[list[list[tuple[int, str]]]] = []
    current: list[list[tuple[int, str]]] = []
    for unit in units:
        size = sum(_tokens(u) for u in current)
        if current and size + _tokens(unit) > max_tokens:
            windows.append(current)
            # carry trailing units as overlap, but never the whole previous window
            carry, carried = [], 0
            for prev in reversed(current[1:]):
                if carried + _tokens(prev) > overlap_tokens:
                    break
                carry.insert(0, prev)
                carried += _tokens(prev)
            current = carry
        current.append(unit)
    if current:
        windows.append(current)

    packed = []
    for window in windows:
        flat: list[tuple[int, str]] = []
        for i, unit in enumerate(window):
            if i:
                flat.append((unit[0][0], ""))
            flat.extend(unit)
        packed.append(flat)
    return packed


def _collect(node: _Node, path: list[str], max_tokens: int, overlap: int,
             out: list[tuple[str, list[tuple[int, str]]]], prefix: list[tuple[int, str]] | None = None) -> None:
    here = path + [node.title] if node.title else path
    section = " > ".join(here)
    prefix = prefix or []

    whole = prefix + _strip_blank_edges(node.all_lines())
    if whole and _tokens(whole) <= max_tokens:
        out.append((section, whole))
        return

    own = _strip_blank_edges(
        ([(node.heading_line, f"{'#' * node.level} {node.title}")] if node.heading_line else []) + node.body
    )
    own = prefix + own
    carry = None
    if own:
        if node.children and _tokens(own) < _MIN_STANDALONE_TOKENS:
            carry = own  # too small to stand alone — give it to the first child as context
        else:
            for window in _pack(own, max_tokens, overlap):
                out.append((section, window))

    for i, child in enumerate(node.children):
        _collect(child, here, max_tokens, overlap, out, prefix=carry if i == 0 else None)


def chunk_document(doc: Document, max_tokens: int = 350, overlap_tokens: int = 50) -> list[Chunk]:
    tree = _parse_tree(doc.text)
    raw: list[tuple[str, list[tuple[int, str]]]] = []
    _collect(tree, [], max_tokens, overlap_tokens, raw)

    # A single top-level H1 is the document title; leave it out of section paths.
    single_h1 = len(tree.children) == 1 and tree.children[0].level == 1

    chunks = []
    for section, lines in raw:
        text = _BLANK_RUNS.sub("\n\n", "\n".join(t for _, t in lines)).strip()
        if not text:
            continue
        parts = section.split(" > ")
        if single_h1 and len(parts) > 1:
            parts = parts[1:]
        section_label = " > ".join(parts) or doc.title
        header = f"{doc.title} | {doc.product} {doc.version} | {doc.doc_type} | {section_label}"
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#c{len(chunks)}",
                text=text,
                embed_text=f"{header}\n\n{text}",
                section=section_label,
                chunk_index=len(chunks),
                line_start=min(n for n, _ in lines) + doc.line_offset,
                line_end=max(n for n, _ in lines) + doc.line_offset,
                token_count=estimate_tokens(text),
                content_hash=content_hash,
                doc=doc,
            )
        )
    return chunks
