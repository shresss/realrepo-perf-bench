"""Month-end statement export.

    python -m ledgerly.report --db data/visible.db --month 2026-08 --out out/statements.json

For every customer, lists the invoices issued in the month (oldest first) with
their line items, and the amount still owed across the non-void ones.
"""
import argparse
import sys

from .config import Settings
from .db.connection import connect
from .reporting.export import write_statements
from .services.statements import StatementService


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ledgerly.report", description="Month-end statement export.")
    parser.add_argument("--db", required=True, help="path to the Ledgerly database")
    parser.add_argument("--month", required=True, help="month to export, YYYY-MM")
    parser.add_argument("--out", required=True, help="where to write the JSON export")
    args = parser.parse_args(argv)

    settings = Settings()
    conn = connect(args.db)
    try:
        statements = StatementService(conn, settings).build(args.month)
    finally:
        conn.close()
    write_statements(args.out, args.month, statements)
    print(f"wrote {len(statements)} statements to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
