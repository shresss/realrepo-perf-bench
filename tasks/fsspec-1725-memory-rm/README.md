# fsspec-1725-memory-rm

Make a staging cleanup job on fsspec's in-memory filesystem (pipe writes, manifest rm, recursive rm) fast while preserving every rm, write and type-probe behavior.

- Upstream repository: https://github.com/fsspec/filesystem_spec (BSD-3-Clause)
- Base commit: `176efbe02179f30b5862bf7444a383b8e62f87df`
- Expert reference: `03e89cc1713d178bec349704e99b5c075de66d74` from https://github.com/fsspec/filesystem_spec/pull/1725
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `performance-cleanup-1000` | 13.83 | 0.2688 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-exists-shortcut.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
