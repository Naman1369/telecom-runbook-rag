# Evaluation

Run with `python scripts/evaluate.py`. It uses 21 golden questions in `eval/golden_set.jsonl`:

- 17 answerable questions: the same incident asked against both releases where the commands differ.
- 2 **trap** questions: a feature exists only in the *other* release (e.g. the built-in VSWR test
  in HX-5G 22.3). The answer must not contain the other release's command.
- 2 **out-of-scope** questions: the correct response is "not found".

Raw results are written to `eval/results/` (git-ignored).

## Latest run — 29 Sep 2026

Config: `gemini-3.5-flash-lite`, `gemini-embedding-001` (768-d), top-k 5, threshold 0.65, 52 chunks.

| Metric | Target | Result |
| --- | --- | --- |
| Correct source citation | ≥ 90% | **100%** (17/17) |
| Scoped to the correct version | ≥ 95% | **100%** (17/17) |
| Version-specific command correct | — | **100%** (15/15) |
| No wrong-release command leaked (incl. traps) | — | **100%** (5/5) |
| Correct answered / not-found status | — | **100%** (19/19) |
| Median latency | < 3 s | **1.29 s** (p90 1.84 s) |

Out-of-scope questions below the threshold return in under 10 ms because the LLM is not called.

### Caveats

- The corpus is small (10 docs, 52 chunks) and synthetic, and the golden set was written by the team.
  Results on a real operator corpus will be lower. Grow `golden_set.jsonl` as documents are added.
- Latency depends on Gemini load. Full Flash models were overloaded during testing (see DESIGN.md).
