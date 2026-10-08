# cattrs-464-linecache-dedup

Optimize repeated cattrs configuration conversion while preserving typed results and debugging behavior.

- Upstream repository: https://github.com/python-attrs/cattrs (MIT)
- Base commit: `5b1fa6a6d0dc43ec4ad1c71f2ba05ee5ab3ded6e`
- Expert reference: `88d4758ebc1d1ab7ce9b8e8ceb94cc3b15a5e5c9` from https://github.com/python-attrs/cattrs/pull/464
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `roundtrip-3000` | 6.73 | 0.3854 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-drop-field.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
