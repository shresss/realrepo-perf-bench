# pystac-295-generate-subcatalogs

Organize imagery catalogs faster while preserving hierarchy and item metadata.

- Upstream repository: https://github.com/stac-utils/pystac (Apache-2.0)
- Base commit: `a29705f7a3ce23b02453141e061805c62088293e`
- Expert reference: `4a2122d16ac07fe0476e95f1cd190476d90eeace` from https://github.com/stac-utils/pystac/pull/295
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `catalog-4000` | 3.41 | 0.5412 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-discard-existing.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
