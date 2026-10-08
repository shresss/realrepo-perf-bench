# lark-1419-interactive-accepts

Interactive parsing slows down on longer configuration transcripts when callers request valid next terminals at each token.

- Upstream repository: https://github.com/lark-parser/lark (MIT)
- Base commit: `29bb78b89896b423723deb3a3592fb71d016ec09`
- Expert reference: `3a29aee4c3919f46ebeefbbed358fb32a20c8a4b` from https://github.com/lark-parser/lark/pull/1419
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `records-800` | 19.30 | 0.2276 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-choices.patch`: a fast but incorrect fix; must fail correctness
- `controls/partial.patch`: a partial fix; must miss the speed bar

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
