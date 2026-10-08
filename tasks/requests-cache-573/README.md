# requests-cache-573

Make periodic SQLiteCache.remove_expired_responses() maintenance in requests-cache substantially cheaper while preserving expiry, redirect, persistence and old-cache-file behavior.

- Upstream repository: https://github.com/requests-cache/requests-cache (BSD-2-Clause)
- Base commit: `8fa9c24b23d143db645cf24a24764597b04caccc`
- Expert reference: `2bd683658e17602a826a26b864a399b68181ee33` from https://github.com/requests-cache/requests-cache/pull/573
- Reference provenance: `authored-repair` (the merged fix plus a small correction we wrote, because the merged fix alone fails a correctness case)

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `fresh-1000` | 2.06 | 0.6964 |
| `legacy-4000` | 2.67 | 0.6119 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-public-pr.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | False | False |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | False | False |
