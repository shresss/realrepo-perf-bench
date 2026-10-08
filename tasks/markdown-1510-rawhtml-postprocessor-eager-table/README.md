# markdown-1510-rawhtml-postprocessor-eager-table

Improve API documentation conversion while preserving public behavior.

- Upstream repository: https://github.com/Python-Markdown/markdown (BSD-3-Clause)
- Base commit: `f6cfc5cca3dd2c313d2fa547b7c88dac656ae506`
- Expert reference: `1caf02892487cead069cb0c4bcdd1e876ca6b590` from https://github.com/Python-Markdown/markdown/pull/1510
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `api-400` | 11.58 | 0.2938 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-skip-restore.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
