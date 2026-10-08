# dbt-11099-select-children

Improve exported warehouse lineage selections while preserving membership, depth, edge types and caller graph behavior.

- Upstream repository: https://github.com/dbt-labs/dbt-core (Apache-2.0)
- Base commit: `ff6745c79532d50139d553f3b088c5d783b4f2dd`
- Expert reference: `1472b86ee297c923a463232320920999f6210c78` from https://github.com/dbt-labs/dbt-core/pull/11099
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `lineage-1000` | 4.10 | 0.4936 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative.patch`: a fast but incorrect fix; must fail correctness
- `controls/partial-children.patch`: a partial fix; must miss the speed bar

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
