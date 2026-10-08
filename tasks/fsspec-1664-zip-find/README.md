# fsspec-1664-zip-find

Optimize ZIP dataset discovery in fsspec while preserving listing behavior.

- Upstream repository: https://github.com/fsspec/filesystem_spec (BSD-3-Clause)
- Base commit: `ee98ae3cc43c68455d4632cb23dd57bb702e5684`
- Expert reference: `7793ab89a56d70814de6d123c257e81f8e5bd52f` from https://github.com/fsspec/filesystem_spec/pull/1664
- Reference provenance: `authored-repair` (the merged fix plus a small correction we wrote, because the merged fix alone fails a correctness case)

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `bundle-1344` | 11.70 | 0.2922 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-drop-directories.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
