#!/usr/bin/env bash
# Reference (expert) fix. The export read the month's data one row at a time from
# three nested places: invoices per customer, lines per invoice, and product names
# per line through a catalog cache that was cleared for every invoice. Replace
# them with two set-based reads (the month's invoices; the month's lines joined to
# products, LEFT JOIN so retired products still count) grouped in memory, plus the
# customer list: 3 statements regardless of size. Output is identical.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$HERE/repositories.py" /app/ledgerly/db/repositories.py
cp "$HERE/statements.py" /app/ledgerly/services/statements.py
cd /app && python -m pytest -q tests
