# tomlkit-503-supertable-merge-deepcopy

Improve inventory document processing while preserving public behavior.

- Upstream repository: https://github.com/python-poetry/tomlkit (MIT)
- Base commit: `0ad22b5d2efe17a22acaf787da4388c73e7e3fb2`
- Expert reference: `fdfbc8a18c5fd5cfdcaaf11bfd59c4151da1f2ca` from https://github.com/python-poetry/tomlkit/pull/503
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `inventory-150` | 17.25 | 0.2407 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/partial-trivia.patch`: a partial fix; must miss the speed bar

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
