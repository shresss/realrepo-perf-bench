# feature-engine-987

Speed up feature_engine MathFeatures.fit_transform row reductions in the feature-engine repository while preserving reducer, missing-value and DataFrame semantics.

- Upstream repository: https://github.com/feature-engine/feature_engine (BSD-3-Clause)
- Base commit: `2564cb7aa55188d736019facc942f07acaeb12c7`
- Expert reference: `4b3cd03e05011cc5e575c6e60e4bf97637eff97a` from https://github.com/feature-engine/feature_engine/pull/987
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `scale-32000` | 5.64 | 0.421 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-ddof.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | False | False |
| GPT-6 Astra | True | True |
