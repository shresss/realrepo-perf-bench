# ibis-8445-name-exponential

Speed up daily smart-meter rollups and time-of-use billing through ibis and DuckDB while preserving query results and exact default expression names.

- Upstream repository: https://github.com/ibis-project/ibis (Apache-2.0)
- Base commit: `a75531526584c5c5802578fe0680c6f7a0007af1`
- Expert reference: `7667328ada9cb8ef6bb4c456636c6a7ccab2ad1a` from https://github.com/ibis-project/ibis/pull/8445
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `performance-daily-24` | 5.98 | 0.4088 |
| `performance-tariff-20` | 7.77 | 0.3587 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-collapsed-name.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | False | False |
| GPT-6 Astra | True | True |
