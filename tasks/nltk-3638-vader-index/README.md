# nltk-3638-vader-index

Make NLTK VADER SentimentIntensityAnalyzer.polarity_scores fast on long documents while keeping every score bit-identical, including first-occurrence context for repeated words.

- Upstream repository: https://github.com/nltk/nltk (Apache-2.0)
- Base commit: `7377ae521d6265679fdae18c006fe048ccf1dd0b`
- Expert reference: `c04f6d88e15cc18b55c296fd5ef1be4af7ab9a6e` from https://github.com/nltk/nltk/pull/3638
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `perf-transcripts-8000` | 2.62 | 0.6178 |
| `perf-transcripts-8000-hidden` | 2.62 | 0.6181 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-partial-memo-index.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
