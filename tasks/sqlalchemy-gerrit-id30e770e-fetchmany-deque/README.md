# sqlalchemy-gerrit-id30e770e-fetchmany-deque

Improve synchronous bulk insert result throughput while preserving complete results.

- Upstream repository: https://github.com/sqlalchemy/sqlalchemy (MIT)
- Base commit: `6888cf79db79d5e5660300ccf2a2a91f1eecf75f`
- Expert reference: `7782e2b3ad5a6a8c860f689f345a00ae47db6c7f` from https://github.com/sqlalchemy/sqlalchemy/commit/319304e7c9e5c6c2e42513b81f85aa6b238495b5
- Reference provenance: `public-commit`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `insert-returning-200000` | 5.45 | 0.4285 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
