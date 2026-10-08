# sqlglot-3901-apply-backtrack

Speed up SQLGlot T-SQL parsing and Spark/T-SQL generation for reporting views with many OUTER/CROSS APPLY lookups while preserving generated SQL, the parsed join structure (including nested-join syntax) and the public API.

- Upstream repository: https://github.com/tobymao/sqlglot (MIT)
- Base commit: `3e5e7300ec184024f871669db48d68476b3fa4df`
- Expert reference: `bea3c08e46a020d8545b702c77f0db18c99f1c55` from https://github.com/tobymao/sqlglot/pull/3901
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `perf-customer360-14` | 8.99 | 0.3335 |
| `perf-event_enrichment-20` | 9.79 | 0.3196 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-subquery-only-guard.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | False | False |
| GPT-6 Astra | True | True |
