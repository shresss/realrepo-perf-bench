# pyjanitor-1644

Optimize pyjanitor DataFrame.conditional_join for large unsorted single-inequality joins with keep first/last while preserving which original right rows are selected.

- Upstream repository: https://github.com/pyjanitor-devs/pyjanitor (MIT)
- Base commit: `da03bfd019e5b01bc9406910d0acd46dd9461dee`
- Expert reference: `8367153dcb435b80048134a51ccb161e148881d2` from https://github.com/pyjanitor-devs/pyjanitor/pull/1644
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `scale-320000` | 3.68 | 0.5211 |
| `greater-scale-320000` | 4.10 | 0.4935 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-sorted-position.patch`: a fast but incorrect fix; must fail correctness
- `controls/negative-strict-inclusive.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
