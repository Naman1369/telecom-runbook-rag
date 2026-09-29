"""Ask a question from the terminal.

Usage:
    python scripts/ask.py "BGP peer is down, how do I reset it?" --product AX-9000 --version 8.1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.main import get_pipeline  # noqa: E402
from app.rag import QueryRequest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--product")
    parser.add_argument("--version")
    parser.add_argument("--json", action="store_true", help="print the raw JSON response")
    args = parser.parse_args()

    result = get_pipeline().answer(QueryRequest(args.question, product=args.product, version=args.version))
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"\n[{result['product']} {result['version']}] {result['status'].upper()}"
          f"  ({result['latency_ms']['total']} ms)\n")
    print(result["summary"], "\n")
    for i, step in enumerate(result["steps"], 1):
        cmd = f"\n      $ {step['command']}" if step["command"] else ""
        print(f"  {i}. {step['instruction']} [{', '.join(map(str, step['citations']))}]{cmd}")
    for w in result["warnings"]:
        print(f"  ! {w['text']}")
    print()
    for c in result["citations"]:
        print(f"  [{c['id']}] {c['title']} {c['version']} — {c['section']} "
              f"(L{c['line_start']}-{c['line_end']}, score {c['score']})")


if __name__ == "__main__":
    main()
