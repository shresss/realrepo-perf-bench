# iceberg-2674-summary-metadata-hoist

Optimize PyIceberg Table.append commits on a long-history SqlCatalog table (apache/iceberg-python) while preserving snapshot summaries and transaction semantics.

- Upstream repository: https://github.com/apache/iceberg-python (Apache-2.0)
- Base commit: `d3eb149fe99b14e714a06e727b69cd617c6c052d`
- Expert reference: `1f9c46b4b567add9821583a4717641d70cebee1d` from https://github.com/apache/iceberg-python/pull/2674
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `reload-1000` | 3.82 | 0.5114 |
| `backfill-500-s11` | 4.26 | 0.4846 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-partial-hoist.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
