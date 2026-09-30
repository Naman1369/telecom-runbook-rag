import pytest

from app.ingest.chunking import _parse_tree


@pytest.mark.parametrize("opening,closing", [("```sh", "```"), ("~~~~", "~~~~~"), ("   ```", "   ```")])
def test_fenced_comments_are_not_section_headings(opening, closing):
    text = f"# Runbook\n## Recovery\n{opening}\n# restart daemon\nrun command\n{closing}\n## Verify\ncheck"
    tree = _parse_tree(text)
    assert [n.title for n in tree.children[0].children] == ["Recovery", "Verify"]
    assert tree.all_lines() == list(enumerate(text.splitlines(), 1))


def test_shorter_or_mismatched_fence_does_not_close_code():
    tree = _parse_tree("# Runbook\n````\n```\n~~~\n# still code\n````\n## Real")
    assert [n.title for n in tree.children[0].children] == ["Real"]


def test_unclosed_fence_preserves_remaining_lines_as_code():
    tree = _parse_tree("# Runbook\n```\n# code")
    assert tree.children[0].children == []
    assert tree.children[0].body[-1] == (3, "# code")
