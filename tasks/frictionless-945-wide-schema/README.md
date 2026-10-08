# frictionless-945-wide-schema

Improve wide-table schema inference through Resource.infer while preserving names, types and field independence.

- Upstream repository: https://github.com/frictionlessdata/frictionless-py (MIT)
- Base commit: `5c1817f1d8d1931a6017024b24300a769f91f9a1`
- Expert reference: `950be0769690ce666dd99f10df73dc5c56bb4a4c` from https://github.com/frictionlessdata/frictionless-py/pull/945
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `columns-1280` | 8.94 | 0.3344 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-string-types.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
