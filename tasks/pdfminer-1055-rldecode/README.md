# pdfminer-1055-rldecode

Speed up pdfminer.six text extraction with image export (extract_text_to_fp output_dir) on RunLength-encoded scanned images while preserving every exported byte.

- Upstream repository: https://github.com/pdfminer/pdfminer.six (MIT)
- Base commit: `541a0c86623a4356a481279f87973419b3248f9a`
- Expert reference: `a3ffcb0228757927fb658a3af1ae46090d92adb5` from https://github.com/pdfminer/pdfminer.six/pull/1055
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `fax-12` | 6.57 | 0.3902 |
| `drawing-1` | 26.47 | 0.1943 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-ignore-eod.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | False |
