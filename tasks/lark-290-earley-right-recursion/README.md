# lark-290-earley-right-recursion

Improve right-recursive parsing throughput while preserving complete trees and grammar behavior.

- Upstream repository: https://github.com/lark-parser/lark (MIT)
- Base commit: `bb22c84df37f3d30144c90f7a4d9416a76364a2d`
- Expert reference: `870a7611cba40bcbdddad17a085984c7d8806d99` from https://github.com/lark-parser/lark/pull/290
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `sequence-500` | 7.90 | 0.3558 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-token-values.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | False | False |
| GPT-6 Astra | True | True |
