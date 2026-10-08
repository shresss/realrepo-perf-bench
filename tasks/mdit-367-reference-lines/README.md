# mdit-367-reference-lines

Improve public Markdown rendering throughput while preserving reference definitions, titles, duplicate tracking and token maps.

- Upstream repository: https://github.com/executablebooks/markdown-it-py (MIT)
- Base commit: `da45c8764b2077425c091fa1811bbb1c5f211bd1`
- Expert reference: `9e93bd554147ffb8582581e14620c7611103d2ff` from https://github.com/executablebooks/markdown-it-py/pull/367
- Reference provenance: `authored-repair` (the merged fix plus a small correction we wrote, because the merged fix alone fails a correctness case)

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `changelog-600` | 4.02 | 0.4984 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-duplicate.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
