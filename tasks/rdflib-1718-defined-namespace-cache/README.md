# rdflib-1718-defined-namespace-cache

Improve OWL RL graph-reasoning throughput while preserving closure and namespace semantics.

- Upstream repository: https://github.com/RDFLib/rdflib (BSD-3-Clause)
- Base commit: `273154fc5cbe4e5f80c1fe45fc1d12893264c4cc`
- Expert reference: `a10198e996d1dc2eb293542fba3a0bf63c088aae` from https://github.com/RDFLib/rdflib/pull/1718
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `closure-600` | 2.38 | 0.648 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-skip-validation.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
