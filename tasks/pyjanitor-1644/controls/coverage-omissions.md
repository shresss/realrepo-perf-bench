# Coverage boundaries — not a full-suite green claim

## What has been checked

- Base/reference/ordinary naive/legitimate alternative all pass the same 12 local
  semantic cases, including two empty-input floors. The subsequent size-only
  calibration amendment left these exact 12 case objects unchanged.
- Join outputs are checked by complete normalized positional-pair digest and
  explicit small-case pairs; inputs and index names are also checked. Independent
  heap-sweep expected outputs agree with brute force over 432 small combinations.
- Local native common selection: 29 baseline/reference/alternative tests pass.
  Reference additionally passes the public PR's 8 new unsorted regression tests.
- Ordinary wrong-order and strictness controls are rejected by four existing
  cases with normal CLI exit 0 and parseable output. No verifier-evasion technique
  or resource-exhaustion control is involved.
- Linux image import/version smoke passes. No Linux native-suite result follows
  from that import check; native Linux checks remain held during calibration.

## Explicit omissions and limitations

- The full upstream suite is not green or completed. A broader reference-file
  run was interrupted after 105 passes and 5 failures; the failures involved missing
  optional numba in deprecated multi-condition paths, followed by Hypothesis
  shrinking timeouts. The full raw trace is retained. The scoped gate excludes
  those paths; numba, polars and pyspark are not installed in this minimal image.
- The protected workload targets one inequality, first/last selection, equal
  left/right sizes, numeric(float64) and representative datetime inputs. It is
  not exhaustive coverage of all join modes, multi-condition joins, asymmetric
  sizes, arbitrary extension dtypes, timezone cases, duplicate column labels,
  arbitrary index classes or all unrelated pyjanitor functions.
- Protected output normalization focuses on selected row identities and input
  preservation. It is not a comprehensive assertion over all possible payload
  columns, every output dtype, or every documented API attribute. Scoped native
  tests add coverage but do not prove equivalence for all inputs.
- These negative receipts use the local Python 3.12.13 translated runtime, not
  the Linux Python 3.12.14 separate-UID verifier. Linux qualification is separate.
- Public source fixes are contamination-prone. Neither original-source task
  construction nor hidden seed variants establish absence of training overlap.
- Three repeats of the same input estimate repeatability, not independent task
  diversity. Diagnostic Python event counts do not measure native slice lengths
  and are not a proof of algorithmic complexity or a substitute for real timing.

The policy remains UNFROZEN. Do not claim a counted task, frontier difficulty,
accepted performance threshold, or complete upstream compatibility from these
checks alone.
