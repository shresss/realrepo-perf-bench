# pyyaml-441-resolver-list-growth

Improve pure-Python YAML application-record loading while preserving parsed values and extension semantics.

- Upstream repository: https://github.com/yaml/pyyaml (MIT)
- Base commit: `7adc0db3f613a82669f2b168edd98379b83adb3c`
- Expert reference: `766b5693d6b4c88b8bdb2b883f9f111388339379` from https://github.com/yaml/pyyaml/pull/441
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `records-6000` | 13.24 | 0.2748 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-skip-wildcard.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
