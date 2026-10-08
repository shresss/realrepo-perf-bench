# kedro-4367

Speed up repeated configuration loading through Kedro's OmegaConfigLoader (catalog and parameters interpolating many globals and runtime params) while preserving resolved values, globals replacement and fresh-loader semantics.

- Upstream repository: https://github.com/kedro-org/kedro (Apache-2.0)
- Base commit: `70734ce00ee46b58c85b4cf04afbe89d32c06758`
- Expert reference: `057de3457a778698001d9fd2f5797ca3b4a9ba3a` from https://github.com/kedro-org/kedro/pull/4367
- Reference provenance: `authored-repair` (the merged fix plus a small correction we wrote, because the merged fix alone fails a correctness case)

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `setter-large` | 8.94 | 0.3343 |
| `stable-large` | 9.66 | 0.3217 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | False | False |
| GPT-6 Astra | True | True |
