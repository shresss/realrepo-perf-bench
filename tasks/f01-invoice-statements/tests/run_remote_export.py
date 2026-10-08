"""Root-owned bootstrap for one black-box Ledgerly export.

The verifier measures this process from the outside.  Database request and
transfer metrics are owned by the separate metered SQLite service, so this
bootstrap deliberately contains no counters or result channel that submitted
code can rewrite.
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    sys.path.insert(0, args.src)
    from ledgerly.report import main as report_main

    return int(
        report_main(
            ["--db", args.db, "--month", args.month, "--out", args.out]
        )
        or 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
