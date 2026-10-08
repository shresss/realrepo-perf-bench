# chardet-203-group-early-exit

Improve whole-document encoding detection throughput while preserving exact results.

- Upstream repository: https://github.com/chardet/chardet (LGPL-2.1-or-later)
- Base commit: `a9286f7b5d78fd1d9542cee5ece2da7989c0688f`
- Expert reference: `1e208b743c3fed378eb3189d8080aba8ba77d730` from https://github.com/chardet/chardet/pull/203
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `utf8-documents-256` | 8.76 | 0.3377 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-confidence.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | False |
