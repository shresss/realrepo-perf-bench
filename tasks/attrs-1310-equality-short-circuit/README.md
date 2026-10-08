# attrs-1310-equality-short-circuit

Improve attrs record reconciliation performance while preserving complete comparison semantics.

- Upstream repository: https://github.com/python-attrs/attrs (MIT)
- Base commit: `feb7a4d892ebcb443736aa431c273fd1cd8ec1d8`
- Expert reference: `a8808a2b3ed2fd1b7c129908fd28ee7b7106a730` from https://github.com/python-attrs/attrs/pull/1310
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `reconcile-2000` | 7.04 | 0.3769 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-first-field.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
