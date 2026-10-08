# datasets-7408-filter-batching

Improve local dataset filtering throughput while preserving row predicate and table semantics.

- Upstream repository: https://github.com/huggingface/datasets (Apache-2.0)
- Base commit: `de062f0552a810c52077543c1169c38c1f0c53fc`
- Expert reference: `704704db6c13c59e9339b92771090ce8318d18ef` from https://github.com/huggingface/datasets/pull/7408
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `filter-120000` | 3.67 | 0.5219 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-local-indices.patch`: a fast but incorrect fix; must fail correctness
- `controls/partial-async-guard.patch`: a partial fix; must miss the speed bar

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
