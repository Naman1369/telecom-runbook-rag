"""Prompt templates live in .md files next to this module so they can be edited without touching code."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_template(name: str) -> Template:
    return Template((PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8"))


def render(name: str, **values: str) -> str:
    return load_template(name).substitute(**values).strip()
