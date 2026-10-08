# sqlparse-848-group-value-quadratic

Improve sqlparse parsing of wide BI query logs while preserving token structure and lineage.

- Upstream repository: https://github.com/andialbrecht/sqlparse (BSD-3-Clause)
- Base commit: `c923da9c5a8e8403dd32efc2171b60a177444d43`
- Expert reference: `939b129e24c0ad5d51368b1aa72fffcaca76f06f` from https://github.com/andialbrecht/sqlparse/pull/848
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `wide-2400` | 5.41 | 0.4297 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-stale-group-value.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
