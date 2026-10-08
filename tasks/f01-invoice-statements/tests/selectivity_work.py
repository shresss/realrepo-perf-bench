"""Trusted cardinality-derived work ceilings for the F01 selectivity gate.

The candidate cannot read the database directly; every SQL result crosses the
verifier-owned service.  A correct three-query export therefore needs at most one
returned row per customer, target-month invoice, and target-month line item.  We
derive a generous row ceiling from those semantic cardinalities, then derive byte
and SQLite VM-step ceilings without using the intentionally inefficient pristine
implementation as the standard of acceptable work.
"""

import math
import sqlite3


ROW_RELATIVE_ALLOWANCE = 0.25
ROW_ABSOLUTE_ALLOWANCE = 10_000
BYTES_PER_ROW_ALLOWANCE = 512
BYTE_ABSOLUTE_ALLOWANCE = 2 * 1024 * 1024
VM_STEPS_PER_RELEVANT_ROW = 50
VM_STEP_ABSOLUTE_ALLOWANCE = 500_000


def relevant_work_profile(path: str, start: str, end: str) -> dict[str, int]:
    """Return verifier-observed semantic cardinalities for ``[start, end)``."""

    conn = sqlite3.connect(path)
    try:
        customers = conn.execute("SELECT count(*) FROM customers").fetchone()[0]
        invoices = conn.execute(
            "SELECT count(*) FROM invoices "
            "WHERE issued_at >= ? AND issued_at < ?",
            (start, end),
        ).fetchone()[0]
        line_items = conn.execute(
            "SELECT count(*) "
            "FROM invoices AS i "
            "JOIN line_items AS li ON li.invoice_id = i.id "
            "WHERE i.issued_at >= ? AND i.issued_at < ?",
            (start, end),
        ).fetchone()[0]
    finally:
        conn.close()
    relevant_rows = customers + invoices + line_items
    return {
        "customers": customers,
        "target_month_invoices": invoices,
        "target_month_line_items": line_items,
        "relevant_rows": relevant_rows,
    }


def selective_work_ceilings(profile: dict[str, int]) -> dict[str, int | str]:
    """Derive deliberately generous but relevance-scaled per-job ceilings.

    The coefficients are a preregistered calibration contract for this pinned
    SQLite verifier, not claims about physical I/O or database-independent cost.
    """

    relevant_rows = profile["relevant_rows"]
    if type(relevant_rows) is not int or relevant_rows < 0:
        raise ValueError("relevant_rows must be a non-negative integer")
    row_allowance = max(
        ROW_ABSOLUTE_ALLOWANCE,
        math.ceil(ROW_RELATIVE_ALLOWANCE * relevant_rows),
    )
    row_ceiling = relevant_rows + row_allowance
    return {
        "derivation": "target-month semantic cardinalities under the pinned SQLite verifier",
        "rows": row_ceiling,
        "response_bytes": row_ceiling * BYTES_PER_ROW_ALLOWANCE + BYTE_ABSOLUTE_ALLOWANCE,
        "vm_steps": relevant_rows * VM_STEPS_PER_RELEVANT_ROW + VM_STEP_ABSOLUTE_ALLOWANCE,
    }
