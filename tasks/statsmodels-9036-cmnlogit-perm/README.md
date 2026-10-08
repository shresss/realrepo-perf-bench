# statsmodels-9036-cmnlogit-perm

Improve conditional multinomial fitting throughput while preserving likelihood, gradient and uncertainty.

- Upstream repository: https://github.com/statsmodels/statsmodels (BSD-3-Clause)
- Base commit: `bb25d1a273d538287d1bcddd0ac20c84cb30c885`
- Expert reference: `24d7bf76f79ce2dcec5871b0ca9a5e3db7614257` from https://github.com/statsmodels/statsmodels/pull/9036
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `panel_fit-400` | 4.56 | 0.4681 |

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
