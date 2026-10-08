# astroid-3051-subclass-mro-hoist

Improve type-check inference in generated framework models while preserving public behavior.

- Upstream repository: https://github.com/pylint-dev/astroid (LGPL-2.1-or-later)
- Base commit: `e56ac290f41f2360e3442b05f285664beafd9020`
- Expert reference: `96c41339f36348e2a3048e2d85566cd95a7ace73` from https://github.com/pylint-dev/astroid/pull/3051
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `infer-3000` | 4.74 | 0.4592 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative.patch`: a fast but incorrect fix; must fail correctness
- `controls/partial.patch`: a partial fix; must miss the speed bar

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
