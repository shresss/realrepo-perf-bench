# flytekit-1535-pickle-batches

Optimize local Flyte workflows that pass collections of application records while preserving task APIs and values.

- Upstream repository: https://github.com/flyteorg/flytekit (Apache-2.0)
- Base commit: `b0cf91818c16867c6ba6d3a052c259771617ca1d`
- Expert reference: `0646bc3448f6f2cbf6bc0ceed9536bdfa6214428` from https://github.com/flyteorg/flytekit/pull/1535
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `performance-records-10000` | 5.33 | 0.433 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
