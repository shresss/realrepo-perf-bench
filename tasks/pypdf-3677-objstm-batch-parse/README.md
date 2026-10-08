# pypdf-3677-objstm-batch-parse

Accelerate copying form-heavy compressed-object PDF envelopes while preserving document content and incremental updates.

- Upstream repository: https://github.com/py-pdf/pypdf (BSD-3-Clause)
- Base commit: `2cfcd7ea9d175f1bbd243043a432a6b9470baa37`
- Expert reference: `cf2e5187b0fccd8a26f7b8fb1a140f42847b53d4` from https://github.com/py-pdf/pypdf/pull/3677
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `performance-forms-250` | 7.27 | 0.3709 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-stale-override.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
