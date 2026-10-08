# pyparsing-584-ignore-comments

Improve parsing throughput for annotated symbol manifests while preserving token semantics.

- Upstream repository: https://github.com/pyparsing/pyparsing (MIT)
- Base commit: `96d44647450463a7b9c0962b03f3aeb0d1f165d5`
- Expert reference: `98ad3e19d611cdfc0919d8fd52ba542dd7e6d779` from https://github.com/pyparsing/pyparsing/pull/584
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `symbols-40000` | 2.37 | 0.649 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-block-only.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
