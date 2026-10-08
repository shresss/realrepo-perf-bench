# statsmodels-9720-vecm-projection

Improve VECM fitting throughput while preserving fitted statistics and forecasts.

- Upstream repository: https://github.com/statsmodels/statsmodels (BSD-3-Clause)
- Base commit: `e4c9ba760c52258d4ef8f2ef22b4fa9948bc3f7b`
- Expert reference: `9a3eb9e5bcd7c5fcc438f117ae09b1da58cce77d` from https://github.com/statsmodels/statsmodels/pull/9720
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `hourly-8760x12` | 13.77 | 0.2694 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/control-alternative.patch`
- `controls/control-naive.patch`
- `controls/control-negative.patch`
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
