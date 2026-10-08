# tomlkit-509-out-of-order-incremental-validation

Optimize service configuration parsing and round-tripping while preserving mutable TOML documents and collision errors.

- Upstream repository: https://github.com/python-poetry/tomlkit (MIT)
- Base commit: `989c1a79787d63806de37934a6c2b041e1f550d8`
- Expert reference: `ae1b6790d99b21bc0a339a5825e7d5e40e7e6f6a` from https://github.com/python-poetry/tomlkit/pull/509
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `logging-24` | 24.20 | 0.2032 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive-v01.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/naive-v02.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | False | False |
