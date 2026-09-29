"""Run Workflow 1: build the version-tagged vector index from data/corpus.

Usage:
    python scripts/ingest.py             # full run with Gemini embeddings
    python scripts/ingest.py --dry-run   # load, clean, chunk and validate only (no API calls)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.config import get_settings  # noqa: E402
from app.ingest.pipeline import build_chunks, run_ingestion, validate_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="validate the corpus without embedding/indexing")
    parser.add_argument("--skip-quality", action="store_true", help="skip embedding quality probes")
    args = parser.parse_args()
    settings = get_settings()

    if args.dry_run:
        documents, chunks, load_errors = build_chunks(settings)
        errors, warnings = validate_corpus(documents, chunks, settings.chunk_tokens)
        print(f"Documents: {len(documents)}   Chunks: {len(chunks)}")
        for c in chunks:
            print(f"  {c.chunk_id:<70} {c.token_count:>4} tok  L{c.line_start}-{c.line_end}  {c.section}")
        for e in load_errors + errors:
            print(f"ERROR   {e}")
        for w in warnings:
            print(f"WARNING {w}")
        return 1 if load_errors or errors else 0

    report = run_ingestion(settings, skip_quality=args.skip_quality)
    print(f"Documents loaded : {report.documents}")
    print(f"Chunks created   : {report.chunks}")
    print(f"Chunks indexed   : {report.indexed}  ({'match' if report.indexed == report.chunks else 'MISMATCH'})")
    for key, n in sorted(report.per_version.items()):
        print(f"  {key:<24} {n} chunks")
    if report.token_stats:
        print(f"Chunk tokens     : {report.token_stats}")
    if report.embedding:
        e = report.embedding
        print(f"Embeddings       : {e['model']}  new={e['embedded']} cached={e['cache_hits']} "
              f"calls={e['api_calls']} retries={e['retries']} cost=${e['cost_usd']:.6f}")
    if report.quality:
        q = report.quality
        print(f"Quality probes   : pass rate {q.get('probe_pass_rate')}  "
              f"nearest-neighbour same product {q.get('nearest_neighbour_same_product')}")
        for p in q.get("probes", []):
            print(f"  {'OK ' if p['ok'] else 'BAD'} related={p['related']:.3f} unrelated={p['unrelated']:.3f}  {p['anchor']}")
    for e in report.load_errors + report.validation_errors:
        print(f"ERROR   {e}")
    for w in report.validation_warnings:
        print(f"WARNING {w}")
    print(f"Finished in {report.seconds}s — {'OK' if report.ok else 'FAILED'}; report: storage/ingest_report.json")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
