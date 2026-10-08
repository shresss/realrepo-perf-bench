# splink-2212-inputcolumn-copy

Make splink 3 real-time record lookups (find_matches_to_new_records + compare_two_records on a DuckDBLinker with a trained model) faster without changing candidates or match weights.

- Upstream repository: https://github.com/moj-analytical-services/splink (MIT)
- Base commit: `ee88655ad96fbc6bdfdb835b110923811c7c8211`
- Expert reference: `7b70d6b58a056ff2b1dfa163a392c132c8a7d476` from https://github.com/moj-analytical-services/splink/pull/2212
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `lookup-gated` | 4.22 | 0.4868 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-mutating-copy.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
