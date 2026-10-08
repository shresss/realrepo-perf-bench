# jinja-1111-constant-expression-folding

Improve Jinja catalog template compilation and rendering while preserving public behavior.

- Upstream repository: https://github.com/pallets/jinja (BSD-3-Clause)
- Base commit: `06238a9dba2f80c17c94b487972aeaa111027de4`
- Expert reference: `09ddf2db4362e461339c5122eb232512723eb126` from https://github.com/pallets/jinja/pull/1111
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `catalog-200000` | 3.88 | 0.5074 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative.patch`: a fast but incorrect fix; must fail correctness
- `controls/partial.patch`: a partial fix; must miss the speed bar

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
