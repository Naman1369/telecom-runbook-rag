"""Measure the PRD success metrics against eval/golden_set.jsonl.

Metrics
- citation accuracy   : answered questions whose citations include an expected source (target ≥ 90%)
- version scoping     : answers whose every citation is from the requested version (target ≥ 95%)
- command accuracy    : expected version-specific command appears in the steps
- trap safety         : no command from the *other* release leaks into the answer
- fallback accuracy   : out-of-scope questions correctly return "not_found"
- median latency      : end-to-end, excluding the pacing sleep (target < 3 s)

Usage:
    python scripts/evaluate.py [--sleep 7] [--only ax81-bgp-soft]
The default sleep keeps free-tier Gemini keys under their requests-per-minute limit.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.config import ROOT_DIR  # noqa: E402
from app.main import get_pipeline  # noqa: E402
from app.rag import QueryRequest  # noqa: E402

GOLDEN = ROOT_DIR / "eval" / "golden_set.jsonl"
RESULTS_DIR = ROOT_DIR / "eval" / "results"


def source_matches(citation: dict, expected: str) -> bool:
    path, _, section = expected.partition("::")
    return citation["source_path"] == path and (not section or section.lower() in citation["section"].lower())


def score_case(case: dict, result: dict) -> dict:
    status = result["status"]
    commands = " || ".join((s.get("command") or "") + " " + s["instruction"] for s in result["steps"])
    text = " ".join([result["summary"], commands] + [w["text"] for w in result["warnings"]])
    checks: dict[str, bool] = {}

    exp_status = case.get("expect_status", "answered")
    if exp_status != "any":
        checks["status"] = status == exp_status
    if status == "answered":
        checks["version_scoped"] = all(c["version"] == case["version"] for c in result["citations"])
        if case.get("expect_sources"):
            checks["citation"] = any(source_matches(c, e) for c in result["citations"] for e in case["expect_sources"])
    if case.get("expect_command") and status == "answered":
        checks["command"] = case["expect_command"].lower() in commands.lower()
    if case.get("forbid_command"):
        checks["no_wrong_version_command"] = case["forbid_command"].lower() not in commands.lower()
    if case.get("expect_text") and status == "answered":
        checks["text"] = case["expect_text"].lower() in text.lower()
    return checks


def pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):.1f}% ({sum(values)}/{len(values)})" if values else "n/a"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=7.0, help="seconds between questions (rate limits)")
    parser.add_argument("--only", help="run a single case id")
    args = parser.parse_args()

    cases = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
    pipeline = get_pipeline()

    rows, latencies = [], []
    for i, case in enumerate(cases):
        if i and args.sleep:
            time.sleep(args.sleep)
        try:
            result = pipeline.answer(QueryRequest(case["question"], product=case["product"], version=case["version"]))
        except Exception as exc:  # noqa: BLE001 — record the failure and continue
            rows.append({"id": case["id"], "error": str(exc), "checks": {"status": False}})
            print(f"ERR  {case['id']:<28} {exc}")
            continue
        checks = score_case(case, result)
        latencies.append(result["latency_ms"]["total"])
        rows.append({"id": case["id"], "status": result["status"], "checks": checks,
                     "latency_ms": result["latency_ms"], "citations": [
                         f"{c['source_path']} :: {c['section']}" for c in result["citations"]],
                     "steps": result["steps"], "summary": result["summary"]})
        flag = "PASS" if all(checks.values()) else "FAIL"
        failed = [k for k, v in checks.items() if not v]
        print(f"{flag} {case['id']:<28} {result['status']:<10} {result['latency_ms']['total']:>5} ms"
              f"{'  failed: ' + ', '.join(failed) if failed else ''}")

    def collect(key: str) -> list[bool]:
        return [r["checks"][key] for r in rows if key in r["checks"]]

    summary = {
        "cases": len(rows),
        "all_checks_passed": pct([all(r["checks"].values()) for r in rows]),
        "citation_accuracy": pct(collect("citation")),
        "version_scoping": pct(collect("version_scoped")),
        "command_accuracy": pct(collect("command")),
        "trap_safety": pct(collect("no_wrong_version_command")),
        "status_accuracy": pct(collect("status")),
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "p90_latency_ms": sorted(latencies)[int(0.9 * (len(latencies) - 1))] if latencies else None,
    }
    print("\n" + "\n".join(f"{k:<20} {v}" for k, v in summary.items()))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(f"\nSaved {out.relative_to(ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
