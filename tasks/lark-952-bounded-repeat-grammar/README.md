# lark-952-bounded-repeat-grammar

Improve bounded grammar construction while preserving token and range semantics.

- Upstream repository: https://github.com/lark-parser/lark (MIT)
- Base commit: `8b50786ca1d1d5c23dc556e68188dc521523210c`
- Expert reference: `7ee1409128c378c7e77bfac8018fe46485f4bf77` from https://github.com/lark-parser/lark/pull/952
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `compile-200` | 51.96 | 0.1387 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-upper-bound.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | True | False |
| GPT-6 Astra | True | False |
