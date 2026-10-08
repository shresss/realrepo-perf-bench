# pyjanitor-1681-ne-keep

Speed up pyjanitor DataFrame.conditional_join for a single not-equal condition with keep first/last on daily shipment partitions while preserving selected rows, null semantics and output row order.

- Upstream repository: https://github.com/pyjanitor-devs/pyjanitor (MIT)
- Base commit: `aa1003ae170bfbf98e351f4e287b951be9654ef6`
- Expert reference: `f3ef4546ddb9eae8af8bd672fc5228693bec32fc` from https://github.com/pyjanitor-devs/pyjanitor/pull/1681
- Reference provenance: `public-pr`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `window-14` | 5.95 | 0.4098 |
| `grouped-14` | 5.65 | 0.4208 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-left-order.patch`: a fast but incorrect fix; must fail correctness
- `controls/negative-null-equal.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | True |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
