# tldextract-283-reverse-suffix-scan

Improve offline batch extraction of deep hostnames while preserving public suffix and URL semantics.

- Upstream repository: https://github.com/john-kurkowski/tldextract (BSD-3-Clause)
- Base commit: `a7ecf90c92c1f1c8f011637437224fc980610237`
- Expert reference: `e1876868048ce9e3c219db9cfdb5b6405ba9d9cc` from https://github.com/john-kurkowski/tldextract/pull/283
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `deep-200000` | 3.27 | 0.5531 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-last-label.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
