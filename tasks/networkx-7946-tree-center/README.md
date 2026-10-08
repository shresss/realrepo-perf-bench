# networkx-7946-tree-center

Optimize NetworkX public unrooted tree-isomorphism batches while preserving valid mappings and graph behavior.

- Upstream repository: https://github.com/networkx/networkx (BSD-3-Clause)
- Base commit: `9d96e778b5c2fb3781ab4a4069ab36fbb17ba467`
- Expert reference: `a986762f2a1919126df2174644232c92c58be2be` from https://github.com/networkx/networkx/pull/7946
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `schema-3000` | 20.19 | 0.2225 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-unguarded.patch`: a fast but incorrect fix; must fail correctness
- `controls/partial-internal-vertices.patch`: a partial fix; must miss the speed bar

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
