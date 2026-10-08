# mesa-3800

Make Mesa's EventList fast under repeated event cancellation and rescheduling (len, is_empty, drain) while preserving ordering, cancellation and clear/pop lifecycle behavior.

- Upstream repository: https://github.com/mesa/mesa (Apache-2.0)
- Base commit: `0fa90d09838f2859c0f6c3c3be3e7444e64ed9f4`
- Expert reference: `aa25132ebe6a9ff7596bdef72d4f2f61cae11051` from https://github.com/mesa/mesa/pull/3800
- Reference provenance: `authored-repair` (the merged fix plus a small correction we wrote, because the merged fix alone fails a correctness case)

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `scale-6000` | 4.42 | 0.4758 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-public-reference.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | False | False |
| GPT-6 Astra | True | True |
