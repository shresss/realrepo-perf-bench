# pypdf-3679-name-quadratic

Speed up reading and re-saving PDFs containing long escaped names while preserving decoded names, emitted bytes, and content-stream behavior.

- Upstream repository: https://github.com/py-pdf/pypdf (BSD-3-Clause)
- Base commit: `cf2e5187b0fccd8a26f7b8fb1a140f42847b53d4`
- Expert reference: `3a4e913c4cbee207d72fd63d835740ad9825d1bf` from https://github.com/py-pdf/pypdf/pull/3679
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `resave-depth12` | 22.43 | 0.2111 |
| `tagged-depth12` | 43.31 | 0.1519 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-ascii-fastpath.patch`: a fast but incorrect fix; must fail correctness
- `controls/negative-no-overlap.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
