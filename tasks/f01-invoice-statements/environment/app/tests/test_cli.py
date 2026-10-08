import json
import sqlite3

from ledgerly.db.connection import SCHEMA
from ledgerly.report import main


def test_cli_writes_json_export(tmp_path, capsys):
    db_path = tmp_path / "ledger.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO customers VALUES (1, 'Mei Chen', 'mei@example.com', 'USD')")
    conn.execute("INSERT INTO products VALUES (1, 'API calls (per 1,000)', 'SKU-000001')")
    conn.execute("INSERT INTO invoices VALUES (1, 1, 'INV-00001-0001', '2026-08-01T00:00:00', 5, 'paid')")
    conn.execute("INSERT INTO line_items VALUES (1, 1, 1, 10, 1000)")
    conn.commit()
    conn.close()

    out = tmp_path / "out" / "statements.json"
    assert main(["--db", str(db_path), "--month", "2026-08", "--out", str(out)]) == 0
    assert "wrote 1 statements" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8")) == {
        "month": "2026-08",
        "statements": [{
            "customer_id": 1,
            "name": "Mei Chen",
            "email": "mei@example.com",
            "invoice_count": 1,
            "invoices": [{
                "number": "INV-00001-0001",
                "issued_on": "01 Aug 2026",
                "status": "paid",
                "line_count": 1,
                "items": [{"product": "API calls (per 1,000)", "quantity": 10, "amount": "100.00 USD"}],
                "amount": "95.00 USD",
            }],
            "total_due": "95.00 USD",
        }],
    }
