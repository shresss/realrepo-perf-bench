# fsspec-2091-merge-ranges

Speed up fsspec ReferenceFileSystem.cat over large kerchunk-style reference sets while preserving the bytes returned per key and the coalesced byte ranges requested from the remote store.

- Upstream repository: https://github.com/fsspec/filesystem_spec (BSD-3-Clause)
- Base commit: `669de5e157cd3ce3f9bf71c7bceb7bb31c8c7a55`
- Expert reference: `1724d540ee917f926f93b32b6580e637b3777adc` from https://github.com/fsspec/filesystem_spec/pull/2091
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `performance-variable-6000` | 6.30 | 0.3985 |
| `performance-single-file-6000` | 6.82 | 0.383 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-drop-containment.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | False | False |
| GPT-6 Astra | True | True |
