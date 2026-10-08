"""Warehouse-migration workload for SQLGlot T-SQL reporting views (public profiling aid).

A migration service parses each SQL Server reporting view once with
sqlglot.parse_one(sql, read="tsql") and generates Spark SQL and T-SQL from the
same tree. Views come from two generators:

  customer360       one OUTER/CROSS APPLY (SELECT TOP 1 ... ORDER BY ...) lookup per
                    dimension of a customer profile (size = number of lookups)
  event_enrichment  clickstream enrichment: CROSS/OUTER APPLY over table-valued
                    functions interleaved with ordinary LEFT JOIN ... ON dimension
                    joins (size = number of lookups)
  edge              one fixed statement from EDGE (size = index, seed must be 0)

run() returns both generated SQL strings and a join-structure summary of the tree.
"""

import argparse
import json

LOOKUPS = ["orders", "payments", "tickets", "sessions", "addresses", "invoices", "refunds", "shipments",
           "reviews", "logins", "campaigns", "devices", "subscriptions", "credits", "disputes", "notes",
           "calls", "visits", "carts", "returns", "quotes", "contracts", "alerts", "tasks"]
FUNCS = ["fn_parse_agent", "fn_geo_lookup", "fn_split_tags", "fn_device_class", "fn_session_bucket", "fn_utm_parse"]
DIMS = ["dim_product", "dim_campaign", "dim_store", "dim_channel", "dim_region", "dim_currency"]

EDGE = [
    "SELECT * FROM a CROSS APPLY (SELECT * FROM b WHERE b.id = a.id) AS x",
    "SELECT * FROM a OUTER APPLY (SELECT TOP 1 * FROM b WHERE b.id = a.id ORDER BY b.ts DESC) AS x",
    "SELECT * FROM a CROSS APPLY dbo.fn_split(a.tags, ',') AS s",
    "SELECT * FROM a CROSS APPLY OPENJSON(a.payload) WITH (k VARCHAR(10) '$.k') AS j",
    "SELECT * FROM a CROSS APPLY (SELECT * FROM b) AS x JOIN c ON c.id = x.id",
    "SELECT * FROM a OUTER APPLY (SELECT * FROM b) AS x LEFT JOIN c ON c.id = a.id OUTER APPLY (SELECT 1 AS one) AS y",
    "SELECT * FROM a JOIN b JOIN c ON b.id = c.id ON a.id = b.id",
    "SELECT * FROM a LEFT JOIN b LEFT JOIN c ON b.id = c.id ON a.id = b.id CROSS APPLY (SELECT 1 AS one) AS z",
    "SELECT * FROM a CROSS JOIN b",
    "SELECT * FROM a OUTER APPLY (SELECT * FROM b OUTER APPLY (SELECT * FROM c WHERE c.id = b.id) AS i) AS o",
    "SELECT * FROM a CROSS APPLY (VALUES (1), (2)) AS v(n)",
    "SELECT * FROM a CROSS APPLY b",
    "SELECT * FROM a JOIN b JOIN c JOIN d ON c.id = d.id ON b.id = c.id ON a.id = b.id",
    "SELECT * FROM a CROSS APPLY dbo.fn_tags(a.id) AS f JOIN b JOIN c ON b.id = c.id ON b.k = f.k",
    "SELECT * FROM a INNER JOIN b LEFT JOIN c ON c.id = b.id ON b.id = a.id OUTER APPLY (SELECT TOP 1 * FROM d WHERE d.a_id = a.id) AS x JOIN e JOIN f ON e.id = f.id ON e.id = x.id",
    "SELECT * FROM a, b CROSS APPLY dbo.fn_split(b.tags, ',') AS s",
    "SELECT * FROM a CROSS APPLY (SELECT 1, 2) AS t(x, y) OUTER APPLY (SELECT TOP 1 * FROM b WHERE b.x = t.x) AS u",
    "SELECT * FROM a LEFT JOIN b JOIN c USING (k) ON a.id = b.id",
    "SELECT * FROM a CROSS APPLY (SELECT * FROM b JOIN c JOIN d ON c.id = d.id ON b.id = c.id WHERE b.a_id = a.id) AS x OUTER APPLY dbo.fn_tags(x.id) AS t",
    "WITH s AS (SELECT * FROM a OUTER APPLY (SELECT TOP 1 * FROM b WHERE b.a_id = a.id ORDER BY b.ts DESC) AS x) SELECT * FROM s CROSS APPLY dbo.fn_split(s.tags, ',') AS t",
]


def customer360(n, seed):
    parts = []
    for i in range(n):
        t = LOOKUPS[(i + seed) % len(LOOKUPS)]
        kind = "CROSS" if (i + seed) % 3 == 0 else "OUTER"
        parts.append("%s APPLY (SELECT TOP 1 x.id AS %s_id, x.amount AS %s_amount, x.created_at AS %s_at "
                     "FROM dbo.%s AS x WHERE x.customer_id = c.customer_id AND x.status <> 'void' "
                     "ORDER BY x.created_at DESC) AS l%d" % (kind, t, t, t, t, i))
    cols = ", ".join("l%d.%s_amount" % (i, LOOKUPS[(i + seed) % len(LOOKUPS)]) for i in range(n))
    return ("SELECT c.customer_id, c.name, %s FROM dbo.customers AS c %s WHERE c.region = 'EU'"
            % (cols or "1 AS one", " ".join(parts)))


def event_enrichment(n, seed):
    parts, cols = [], []
    for i in range(n):
        r = (i + seed) % 4
        fn = FUNCS[(i + seed) % len(FUNCS)]
        if r == 0:
            parts.append("CROSS APPLY dbo.%s(e.attr_%d, N'v%d') AS f%d" % (fn, i, seed, i))
        elif r == 1:
            parts.append("OUTER APPLY dbo.%s(e.event_id) AS f%d" % (fn, i))
        elif r == 2:
            parts.append("LEFT JOIN dbo.%s AS d%d ON d%d.id = e.key_%d" % (DIMS[(i + seed) % len(DIMS)], i, i, i))
            cols.append("d%d.name AS d%d_name" % (i, i))
            continue
        else:
            parts.append("OUTER APPLY dbo.%s(e.session_id, %d) AS f%d" % (fn, i, i))
        cols.append("f%d.value AS f%d_value" % (i, i))
    return ("SELECT e.event_id, %s FROM dbo.events AS e %s WHERE e.event_date >= '2024-01-01'"
            % (", ".join(cols) or "1 AS one", " ".join(parts)))


def statement(case, size, seed):
    if type(size) is not int or type(seed) is not int or not 0 <= seed < 1000000:
        raise ValueError("size and seed must be integers, 0 <= seed < 1000000")
    if case == "customer360" and 0 <= size <= 24:
        return customer360(size, seed)
    if case == "event_enrichment" and 0 <= size <= 32:
        return event_enrichment(size, seed)
    if case == "edge" and 0 <= size < len(EDGE) and seed == 0:
        return EDGE[size]
    raise ValueError("unsupported case/size/seed")


def join_shape(tree):
    """One descriptor per Join node in pre-order: side|kind|target type|apply flag|nested joins|ON|USING."""
    from sqlglot import exp

    rows = []
    for node in tree.walk(bfs=False):
        if isinstance(node, exp.Join):
            target = node.this
            apply = target.args.get("cross_apply") if isinstance(target, exp.Lateral) else None
            rows.append("%s|%s|%s|%s|%d|%d|%d" % (
                node.side or "-", node.kind or "-", type(target).__name__,
                {True: "cross", False: "outer", None: "-"}[apply],
                len(target.args.get("joins") or []), node.args.get("on") is not None,
                bool(node.args.get("using"))))
    return rows


def run(case, size, seed):
    import logging

    logging.disable(logging.WARNING)
    import sqlglot

    sql = statement(case, size, seed)
    tree = sqlglot.parse_one(sql, read="tsql")
    return {"spark": tree.sql(dialect="spark"), "tsql": tree.sql(dialect="tsql"), "joins": join_shape(tree)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
