# sqlglot-7823

Speed up SQLGlot parse/qualify/BigQuery SQL generation for deeply chained CTE queries under a partial schema while preserving qualification output, type resolution and the public API.

- Upstream repository: https://github.com/tobymao/sqlglot (MIT)
- Base commit: `aeb2711f3be05bdcfa39a5e7479a0bedb0ca03f7`
- Expert reference: `693b3e3efa5f6e5ec547e29a79cbbe2b84971f21` from https://github.com/tobymao/sqlglot/pull/7823
- Reference provenance: `public-pr-ai-assisted`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `performance-16` | 13.14 | 0.2758 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-return-none.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | False |
