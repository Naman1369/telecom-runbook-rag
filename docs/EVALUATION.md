# Evaluation

Run with `python scripts/evaluate.py`. It uses 21 golden questions in `eval/golden_set.jsonl`:

- 17 answerable questions: the same incident asked against both releases where the commands differ.
- 2 **trap** questions: a feature exists only in the *other* release (e.g. the built-in VSWR test
  in HX-5G 22.3). The answer must not contain the other release's command.
- 2 **out-of-scope** questions: the correct response is "not found".

Raw results are written to `eval/results/` (git-ignored).

## Latest run

_Pending: run after adding `GEMINI_API_KEY` and building the index._
