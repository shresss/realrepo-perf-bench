# pydicom-1734-nested-parent-maintenance

Improve nested DICOM metadata access while preserving mutation and serialization behavior.

- Upstream repository: https://github.com/pydicom/pydicom (MIT)
- Base commit: `090af8f7ca9bcfd9d8f620ccaa9ac220e4315a5a`
- Expert reference: `b6af1fe5a83e520d6fd04845cafb1cb30faffcd1` from https://github.com/pydicom/pydicom/pull/1734
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `indexed-4000` | 18.71 | 0.2311 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-no-parent-links.patch`: a fast but incorrect fix; must fail correctness
- `controls/partial-copy-restoration.patch`: a partial fix; must miss the speed bar

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | False |
| GPT-6 Astra | True | False |
