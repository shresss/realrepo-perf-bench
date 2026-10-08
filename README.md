# realrepo-perf-bench

50 [Harbor](https://harborframework.com)-format tasks that ask a coding agent to make a real Python library faster without changing its behavior. It extends [SWE-fficiency](https://swefficiency.com/) into data-infrastructure code: SQL parsers and optimizers, HTTP caches, remote file systems, document and config formats, data-frame, statistics and pipeline libraries.

- **49 mined tasks.** Each starts from a real merged upstream performance fix. The repository is rolled back to the commit before the fix, and the merged fix is the expert reference. For 6 tasks marked `authored-repair`, the merged fix alone fails a correctness case, so the reference is that fix plus a small correction, and the unrepaired fix is kept as a control that must fail.
- **1 authored task**, `f01-invoice-statements`: an invoicing service with an N+1 query pattern, graded by counting database requests rather than by timing.

Built in two days as a work-trial project (October 2026). This is not an official release of any company.

## Results

Three frontier models through OpenRouter, all with the same Harbor agent (terminus-2, 150-turn limit). One counted attempt per task and model: the first launched attempt that did not fail for infrastructure reasons.

| Model | Pass@1 (95% Wilson CI) | Expert parity (95% CI) |
|---|---|---|
| Claude Opus 5.5 | 48/50, 96% (87-99%) | 39/49, 80% (66-89%) |
| GPT-6 Astra | 48/50, 96% (87-99%) | 41/49, 84% (71-91%) |
| Gemini 3.8 Flash | 42/50, 84% (71-92%) | 39/49, 80% (66-89%) |

- **Pass:** every correctness check passes and, on every graded case, the median paired CPU speedup is at least the square root of the expert's speedup R on that case (half the expert's gain on a log scale).
- **Expert parity:** at least 80% of the expert's speedup on every graded case. Not defined for `f01`, so it is out of 49.
- **Failures:** Opus failed f01-invoice-statements, requests-cache-573; Astra failed requests-cache-573, tomlkit-509-out-of-order-incremental-validation; Flash failed feature-engine-987, fsspec-2091-merge-ranges, ibis-8445-name-exponential, kedro-4367, lark-290-earley-right-recursion, mesa-3800, pypdf-3442-named-dest-cache, sqlglot-3901-apply-backtrack.
- **The clearest gap:** on requests-cache-573, Opus and Astra both made cache cleanup fast by sending the library's generic cleanup method through a new SQLite fast path, which skipped a stated rule (responses that cannot be decoded must still be deleted). The maintainers' own test fails with "expected 1 response, got 2"; the expert fix passes all 44 protected tests.
- Every cell is in [`results/results.csv`](results/results.csv). 13 cells were graded after the original grading cutoff (9 that the verifier had refused on a busy machine, regraded on reserved cores, and 4 Flash runs rerun after rate limits); all 13 passed. Two independently written audit programs recomputed every cell from the raw run files and agree on all 150.

The pass rate at the main bar is high for Opus and Astra (above the 10-60% range a difficulty-targeted benchmark would aim for). Expert parity and the specific failures are the more informative signal.

## What a task contains

| Path | Contents |
|---|---|
| `instruction.md` | What the agent is told: the slow workflow, the command that reproduces it, the behavior that must not change, the speed bar and the time limit. It never names the bottleneck or the fix. |
| `task.toml` | Harbor task configuration and metadata (upstream repo, commits, license). |
| `environment/` | The agent's container: the repository at the base commit and a public profiling aid. |
| `solution/` | The expert reference patch (used by Harbor's oracle agent). |
| `tests/` | The verifier: protected upstream tests, hidden cases, an independent reference program, timing and scoring policy. |
| `controls/` | Patches run through the verifier before any model ran: a different correct fix (must pass), the obvious shallow fix (must fail), and usually a fast but incorrect fix (must fail). |
| `README.md` | Provenance, graded cases with their bars, controls and per-model results. |

## How a task is graded

1. Restore the protected tests and workload over the agent's changes and check their hashes.
2. Run the library's own tests and our cases, including cases the agent never saw, against an independent reference program. Any failure gives reward 0.
3. Time the original and the agent's code alternately, each in a fresh process (CPU time, median of paired ratios).
4. Compare with the task's bar. If the original code does not time consistently, the verifier returns `verifier_invalid` instead of a grade. Symlinks, extra processes and oversized files are blocked.

## Running a task

```
harbor run -p tasks/<task-id> -a oracle
harbor run -p tasks/<task-id> -a terminus-2 -m openrouter/<provider>/<model>
```

Use `tasks-copyleft/<task-id>` for the two copyleft tasks. `task.toml` pins the local image ID used in our runs; if your Harbor version tries to use it, remove the `docker_image` line so it builds from `environment/Dockerfile`. Timing bars were calibrated on one 8-CPU machine; expect some drift elsewhere.

## Disclosures

- The files in each task's `instruction.md`, `task.toml`, `environment/`, `solution/` and `tests/` are byte-for-byte the files that produced the results above, with one exception: the author email line in `f01-invoice-statements/task.toml`. Because they are unmodified, a few grading files still contain build-machine paths and internal notes in provenance fields and code comments.
- `attrs-1310` and `flytekit-1535` use a wider timing tolerance (Tier B: runs within 35% instead of 20%, only when R is at least 4), added after stability results were known.
- Selection rules changed during the build, with times recorded: the per-fix-class cap went from 4 to 6 to 8, and a 90-second baseline CPU budget was added.
- A quiet re-check found some early bars 3.1 to 8.2% too lenient; recomputing the first 36 tasks at the stricter bars changes no pass or fail.
- The upstream fixes are public, so models may have seen them in training.
- One machine, one agent scaffold, one counted attempt per task.

## The 50 tasks

| Task | Upstream repository | Merged fix | License | Notes |
|---|---|---|---|---|
| [`astroid-3051-subclass-mro-hoist`](tasks-copyleft/astroid-3051-subclass-mro-hoist) | pylint-dev/astroid | [#3051](https://github.com/pylint-dev/astroid/pull/3051) | LGPL-2.1-or-later |  |
| [`attrs-1310-equality-short-circuit`](tasks/attrs-1310-equality-short-circuit) | python-attrs/attrs | [#1310](https://github.com/python-attrs/attrs/pull/1310) | MIT | Tier B timing tolerance |
| [`cattrs-464-linecache-dedup`](tasks/cattrs-464-linecache-dedup) | python-attrs/cattrs | [#464](https://github.com/python-attrs/cattrs/pull/464) | MIT |  |
| [`chardet-203-group-early-exit`](tasks-copyleft/chardet-203-group-early-exit) | chardet/chardet | [#203](https://github.com/chardet/chardet/pull/203) | LGPL-2.1-or-later |  |
| [`datasets-7408-filter-batching`](tasks/datasets-7408-filter-batching) | huggingface/datasets | [#7408](https://github.com/huggingface/datasets/pull/7408) | Apache-2.0 |  |
| [`dbt-11099-select-children`](tasks/dbt-11099-select-children) | dbt-labs/dbt-core | [#11099](https://github.com/dbt-labs/dbt-core/pull/11099) | Apache-2.0 |  |
| [`f01-invoice-statements`](tasks/f01-invoice-statements) | authored | none | - | authored task, graded by counting database requests |
| [`feature-engine-987`](tasks/feature-engine-987) | feature-engine/feature_engine | [#987](https://github.com/feature-engine/feature_engine/pull/987) | BSD-3-Clause |  |
| [`flytekit-1535-pickle-batches`](tasks/flytekit-1535-pickle-batches) | flyteorg/flytekit | [#1535](https://github.com/flyteorg/flytekit/pull/1535) | Apache-2.0 | Tier B timing tolerance |
| [`frictionless-945-wide-schema`](tasks/frictionless-945-wide-schema) | frictionlessdata/frictionless-py | [#945](https://github.com/frictionlessdata/frictionless-py/pull/945) | MIT |  |
| [`fsspec-1664-zip-find`](tasks/fsspec-1664-zip-find) | fsspec/filesystem_spec | [#1664](https://github.com/fsspec/filesystem_spec/pull/1664) | BSD-3-Clause | authored-repair |
| [`fsspec-1725-memory-rm`](tasks/fsspec-1725-memory-rm) | fsspec/filesystem_spec | [#1725](https://github.com/fsspec/filesystem_spec/pull/1725) | BSD-3-Clause |  |
| [`fsspec-2091-merge-ranges`](tasks/fsspec-2091-merge-ranges) | fsspec/filesystem_spec | [#2091](https://github.com/fsspec/filesystem_spec/pull/2091) | BSD-3-Clause |  |
| [`ibis-8445-name-exponential`](tasks/ibis-8445-name-exponential) | ibis-project/ibis | [#8445](https://github.com/ibis-project/ibis/pull/8445) | Apache-2.0 |  |
| [`iceberg-2674-summary-metadata-hoist`](tasks/iceberg-2674-summary-metadata-hoist) | apache/iceberg-python | [#2674](https://github.com/apache/iceberg-python/pull/2674) | Apache-2.0 |  |
| [`jinja-1111-constant-expression-folding`](tasks/jinja-1111-constant-expression-folding) | pallets/jinja | [#1111](https://github.com/pallets/jinja/pull/1111) | BSD-3-Clause |  |
| [`kedro-4367`](tasks/kedro-4367) | kedro-org/kedro | [#4367](https://github.com/kedro-org/kedro/pull/4367) | Apache-2.0 | authored-repair |
| [`lark-1419-interactive-accepts`](tasks/lark-1419-interactive-accepts) | lark-parser/lark | [#1419](https://github.com/lark-parser/lark/pull/1419) | MIT |  |
| [`lark-290-earley-right-recursion`](tasks/lark-290-earley-right-recursion) | lark-parser/lark | [#290](https://github.com/lark-parser/lark/pull/290) | MIT |  |
| [`lark-952-bounded-repeat-grammar`](tasks/lark-952-bounded-repeat-grammar) | lark-parser/lark | [#952](https://github.com/lark-parser/lark/pull/952) | MIT |  |
| [`lifelines-1660`](tasks/lifelines-1660) | CamDavidsonPilon/lifelines | [#1660](https://github.com/CamDavidsonPilon/lifelines/pull/1660) | MIT | authored-repair |
| [`markdown-1510-rawhtml-postprocessor-eager-table`](tasks/markdown-1510-rawhtml-postprocessor-eager-table) | Python-Markdown/markdown | [#1510](https://github.com/Python-Markdown/markdown/pull/1510) | BSD-3-Clause |  |
| [`markdown-1621-inline-links`](tasks/markdown-1621-inline-links) | Python-Markdown/markdown | [#1621](https://github.com/Python-Markdown/markdown/pull/1621) | BSD-3-Clause | public-pr-ai-assisted |
| [`mdit-367-reference-lines`](tasks/mdit-367-reference-lines) | executablebooks/markdown-it-py | [#367](https://github.com/executablebooks/markdown-it-py/pull/367) | MIT | authored-repair |
| [`mesa-3800`](tasks/mesa-3800) | mesa/mesa | [#3800](https://github.com/mesa/mesa/pull/3800) | Apache-2.0 | authored-repair |
| [`networkx-7946-tree-center`](tasks/networkx-7946-tree-center) | networkx/networkx | [#7946](https://github.com/networkx/networkx/pull/7946) | BSD-3-Clause |  |
| [`nltk-3638-vader-index`](tasks/nltk-3638-vader-index) | nltk/nltk | [#3638](https://github.com/nltk/nltk/pull/3638) | Apache-2.0 |  |
| [`optuna-bruteforce-series-6650-6649-6705-6646`](tasks/optuna-bruteforce-series-6650-6649-6705-6646) | optuna/optuna | [#6650](https://github.com/optuna/optuna/pull/6650), [#6649](https://github.com/optuna/optuna/pull/6649), [#6705](https://github.com/optuna/optuna/pull/6705), [#6646](https://github.com/optuna/optuna/pull/6646) | MIT | public-pr-series |
| [`pdfminer-1055-rldecode`](tasks/pdfminer-1055-rldecode) | pdfminer/pdfminer.six | [#1055](https://github.com/pdfminer/pdfminer.six/pull/1055) | MIT |  |
| [`pydicom-1734-nested-parent-maintenance`](tasks/pydicom-1734-nested-parent-maintenance) | pydicom/pydicom | [#1734](https://github.com/pydicom/pydicom/pull/1734) | MIT |  |
| [`pyjanitor-1644`](tasks/pyjanitor-1644) | pyjanitor-devs/pyjanitor | [#1644](https://github.com/pyjanitor-devs/pyjanitor/pull/1644) | MIT |  |
| [`pyjanitor-1681-ne-keep`](tasks/pyjanitor-1681-ne-keep) | pyjanitor-devs/pyjanitor | [#1681](https://github.com/pyjanitor-devs/pyjanitor/pull/1681) | MIT |  |
| [`pyparsing-584-ignore-comments`](tasks/pyparsing-584-ignore-comments) | pyparsing/pyparsing | [#584](https://github.com/pyparsing/pyparsing/pull/584) | MIT |  |
| [`pypdf-3442-named-dest-cache`](tasks/pypdf-3442-named-dest-cache) | py-pdf/pypdf | [#3442](https://github.com/py-pdf/pypdf/pull/3442) | BSD-3-Clause |  |
| [`pypdf-3677-objstm-batch-parse`](tasks/pypdf-3677-objstm-batch-parse) | py-pdf/pypdf | [#3677](https://github.com/py-pdf/pypdf/pull/3677) | BSD-3-Clause |  |
| [`pypdf-3679-name-quadratic`](tasks/pypdf-3679-name-quadratic) | py-pdf/pypdf | [#3679](https://github.com/py-pdf/pypdf/pull/3679) | BSD-3-Clause |  |
| [`pystac-295-generate-subcatalogs`](tasks/pystac-295-generate-subcatalogs) | stac-utils/pystac | [#295](https://github.com/stac-utils/pystac/pull/295) | Apache-2.0 |  |
| [`pyyaml-441-resolver-list-growth`](tasks/pyyaml-441-resolver-list-growth) | yaml/pyyaml | [#441](https://github.com/yaml/pyyaml/pull/441) | MIT |  |
| [`rdflib-1718-defined-namespace-cache`](tasks/rdflib-1718-defined-namespace-cache) | RDFLib/rdflib | [#1718](https://github.com/RDFLib/rdflib/pull/1718) | BSD-3-Clause |  |
| [`requests-cache-573`](tasks/requests-cache-573) | requests-cache/requests-cache | [#573](https://github.com/requests-cache/requests-cache/pull/573) | BSD-2-Clause | authored-repair |
| [`splink-2212-inputcolumn-copy`](tasks/splink-2212-inputcolumn-copy) | moj-analytical-services/splink | [#2212](https://github.com/moj-analytical-services/splink/pull/2212) | MIT |  |
| [`sqlalchemy-gerrit-id30e770e-fetchmany-deque`](tasks/sqlalchemy-gerrit-id30e770e-fetchmany-deque) | sqlalchemy/sqlalchemy | [link](https://github.com/sqlalchemy/sqlalchemy/commit/319304e7c9e5c6c2e42513b81f85aa6b238495b5) | MIT | public-commit |
| [`sqlglot-3901-apply-backtrack`](tasks/sqlglot-3901-apply-backtrack) | tobymao/sqlglot | [#3901](https://github.com/tobymao/sqlglot/pull/3901) | MIT |  |
| [`sqlglot-7823`](tasks/sqlglot-7823) | tobymao/sqlglot | [#7823](https://github.com/tobymao/sqlglot/pull/7823) | MIT | public-pr-ai-assisted |
| [`sqlparse-848-group-value-quadratic`](tasks/sqlparse-848-group-value-quadratic) | andialbrecht/sqlparse | [#848](https://github.com/andialbrecht/sqlparse/pull/848) | BSD-3-Clause |  |
| [`statsmodels-9036-cmnlogit-perm`](tasks/statsmodels-9036-cmnlogit-perm) | statsmodels/statsmodels | [#9036](https://github.com/statsmodels/statsmodels/pull/9036) | BSD-3-Clause |  |
| [`statsmodels-9720-vecm-projection`](tasks/statsmodels-9720-vecm-projection) | statsmodels/statsmodels | [#9720](https://github.com/statsmodels/statsmodels/pull/9720) | BSD-3-Clause |  |
| [`tldextract-283-reverse-suffix-scan`](tasks/tldextract-283-reverse-suffix-scan) | john-kurkowski/tldextract | [#283](https://github.com/john-kurkowski/tldextract/pull/283) | BSD-3-Clause |  |
| [`tomlkit-503-supertable-merge-deepcopy`](tasks/tomlkit-503-supertable-merge-deepcopy) | python-poetry/tomlkit | [#503](https://github.com/python-poetry/tomlkit/pull/503) | MIT |  |
| [`tomlkit-509-out-of-order-incremental-validation`](tasks/tomlkit-509-out-of-order-incremental-validation) | python-poetry/tomlkit | [#509](https://github.com/python-poetry/tomlkit/pull/509) | MIT |  |

## License

Third-party code inside each task keeps its upstream license; license texts are in `LICENSES/<task-id>/` and notices in `THIRD_PARTY_NOTICES.md`. No license has been chosen yet for the original material in this repository (verifiers, cases, instructions, documentation).
