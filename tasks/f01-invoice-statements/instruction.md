# The month-end statement export is too slow

In this production-shaped scenario, Ledgerly's month-end statement export has
become the long pole of close. This checkout includes a representative database
and a reproducible workload. The larger target environment uses the same read-only
SQL interface, but has more customers, more invoices, substantial historical data,
and non-local request latency.

Reproduce the production-shaped path:

```sh
cd /app
./workloads/run_visible.sh
```

You may also run the report directly against the sample file while debugging:

```sh
python -m ledgerly.report --db data/visible.db --month 2026-08 \
  --out out/statements.json
```

Make the export substantially faster.

Constraints:

- Preserve the command-line and output contract for every database conforming to
  the documented schema and declared workload family: the
  invocation, arguments, exit behavior, output-path behavior, JSON structure,
  values, and ordering must remain equivalent.
- Keep the existing tests passing: `python -m pytest tests`.
- Do not change the database schema or add dependencies. The job must continue
  to work against both a local database path and the SQLite-compatible target
  exercised by the visible workload.
- Do not modify anything under `workloads/` or `data/`; those are fixtures.

Evaluation first checks the exact report semantics on unseen databases. It then
measures the unmodified and submitted implementations through an evaluator-owned
database service and external clock. The unseen cases vary declared production
dimensions—seed, month, scale, sparsity, skew, retired-product references, and
the amount of out-of-month history—without changing the schema, interface, or
required behavior.
