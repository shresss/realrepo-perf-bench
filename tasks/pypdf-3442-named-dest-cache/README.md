# pypdf-3442-named-dest-cache

Improve pypdf page-copy and PDF-save performance while preserving logical page and destination behavior.

- Upstream repository: https://github.com/py-pdf/pypdf (BSD-3-Clause)
- Base commit: `46a2b04d099a7d2f0396e7b212f06e3922c4abc0`
- Expert reference: `4dc9494e2342d78141c1e1b481012de0e7416bc0` from https://github.com/py-pdf/pypdf/pull/3442
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `manual-300` | 4.49 | 0.4716 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-empty.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | False | False |
| GPT-6 Astra | True | True |
