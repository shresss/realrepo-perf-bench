# lifelines-1660

Speed up lifelines AalenJohansenFitter(calculate_variance=True).fit on large cohorts while preserving incidence, variance, confidence intervals and the event table.

- Upstream repository: https://github.com/CamDavidsonPilon/lifelines (MIT)
- Base commit: `ca6de15a6e66f065cecce54b198c57a5886c4035`
- Expert reference: `bebbb52d333214714a6a42d1e68fb22bcad55f3e` from https://github.com/CamDavidsonPilon/lifelines/pull/1660
- Reference provenance: `authored-repair` (the merged fix plus a small correction we wrote, because the merged fix alone fails a correctness case)

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `scale-8000` | 4.68 | 0.4621 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-public-pr-unrepaired.patch`: a fast but incorrect fix; must fail correctness
- `controls/review-quadratic-numpy.patch`

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | False |
