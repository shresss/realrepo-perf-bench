# markdown-1621-inline-links

Make Python-Markdown render generated index pages with thousands of inline elements fast (markdown.Markdown().convert) without changing the HTML.

- Upstream repository: https://github.com/Python-Markdown/markdown (BSD-3-Clause)
- Base commit: `7be0cff7318f9e0abf8a9481a4238a86e626530a`
- Expert reference: `152a16fb1a926eabbfc5ab1af83f2b6cf9979314` from https://github.com/Python-Markdown/markdown/pull/1621
- Reference provenance: `public-pr-ai-assisted`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `performance-tag-index-3000` | 6.70 | 0.3862 |
| `performance-symbol-index-1500` | 16.23 | 0.2482 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-links-only.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
