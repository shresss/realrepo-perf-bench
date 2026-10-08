"""Independent stdlib-only oracle for sqlglot-3901-apply-backtrack. Never imports SQLGlot or workload.py.

customer360 / event_enrichment: the Spark SQL, T-SQL and join-structure summary are written out from the
view grammar directly (APPLY -> [INNER|LEFT] JOIN LATERAL in Spark, TOP 1 -> trailing LIMIT 1, T-SQL
round-trips with table-valued function names upper-cased, N'..' literals plain in Spark).
edge: fixed golden outputs of the untouched base checkout (3e5e7300), reviewed by hand and identical on the
public reference (bea3c08e); they pin the classic nested-join syntax (JOIN b JOIN c ON .. ON ..), USING,
comma joins, CTEs and APPLY inside derived tables.
"""

LOOKUPS = ["orders", "payments", "tickets", "sessions", "addresses", "invoices", "refunds", "shipments",
           "reviews", "logins", "campaigns", "devices", "subscriptions", "credits", "disputes", "notes",
           "calls", "visits", "carts", "returns", "quotes", "contracts", "alerts", "tasks"]
FUNCS = ["fn_parse_agent", "fn_geo_lookup", "fn_split_tags", "fn_device_class", "fn_session_bucket", "fn_utm_parse"]
DIMS = ["dim_product", "dim_campaign", "dim_store", "dim_channel", "dim_region", "dim_currency"]

LATERAL_CROSS = "-|-|Lateral|cross|0|0|0"
LATERAL_OUTER = "-|-|Lateral|outer|0|0|0"
DIM_JOIN = "LEFT|-|Table|-|0|1|0"

EDGE_EXPECTED = [
    ('SELECT * FROM a INNER JOIN LATERAL (SELECT * FROM b WHERE b.id = a.id) AS x',
     'SELECT * FROM a CROSS APPLY (SELECT * FROM b WHERE b.id = a.id) AS x',
     ['-|-|Lateral|cross|0|0|0']),
    ('SELECT * FROM a LEFT JOIN LATERAL (SELECT * FROM b WHERE b.id = a.id ORDER BY b.ts DESC LIMIT 1) AS x',
     'SELECT * FROM a OUTER APPLY (SELECT TOP 1 * FROM b WHERE b.id = a.id ORDER BY b.ts DESC) AS x',
     ['-|-|Lateral|outer|0|0|0']),
    ("SELECT * FROM a INNER JOIN LATERAL dbo.FN_SPLIT(a.tags, ',') AS s",
     "SELECT * FROM a CROSS APPLY dbo.FN_SPLIT(a.tags, ',') AS s",
     ['-|-|Lateral|cross|0|0|0']),
    ("SELECT * FROM a INNER JOIN LATERAL OPENJSON(a.payload) WITH (k VARCHAR(10) '$.k') AS j",
     "SELECT * FROM a CROSS APPLY OPENJSON(a.payload) WITH (k VARCHAR(10) '$.k') AS j",
     ['-|-|Lateral|cross|0|0|0']),
    ('SELECT * FROM a INNER JOIN LATERAL (SELECT * FROM b) AS x JOIN c ON c.id = x.id',
     'SELECT * FROM a CROSS APPLY (SELECT * FROM b) AS x JOIN c ON c.id = x.id',
     ['-|-|Lateral|cross|0|0|0', '-|-|Table|-|0|1|0']),
    ('SELECT * FROM a LEFT JOIN LATERAL (SELECT * FROM b) AS x LEFT JOIN c ON c.id = a.id LEFT JOIN LATERAL (SELECT 1 AS one) AS y',
     'SELECT * FROM a OUTER APPLY (SELECT * FROM b) AS x LEFT JOIN c ON c.id = a.id OUTER APPLY (SELECT 1 AS one) AS y',
     ['-|-|Lateral|outer|0|0|0', 'LEFT|-|Table|-|0|1|0', '-|-|Lateral|outer|0|0|0']),
    ('SELECT * FROM a JOIN b JOIN c ON b.id = c.id ON a.id = b.id',
     'SELECT * FROM a JOIN b JOIN c ON b.id = c.id ON a.id = b.id',
     ['-|-|Table|-|1|1|0', '-|-|Table|-|0|1|0']),
    ('SELECT * FROM a LEFT JOIN b LEFT JOIN c ON b.id = c.id ON a.id = b.id INNER JOIN LATERAL (SELECT 1 AS one) AS z',
     'SELECT * FROM a LEFT JOIN b LEFT JOIN c ON b.id = c.id ON a.id = b.id CROSS APPLY (SELECT 1 AS one) AS z',
     ['LEFT|-|Table|-|1|1|0', 'LEFT|-|Table|-|0|1|0', '-|-|Lateral|cross|0|0|0']),
    ('SELECT * FROM a CROSS JOIN b',
     'SELECT * FROM a CROSS JOIN b',
     ['-|CROSS|Table|-|0|0|0']),
    ('SELECT * FROM a LEFT JOIN LATERAL (SELECT * FROM b LEFT JOIN LATERAL (SELECT * FROM c WHERE c.id = b.id) AS i) AS o',
     'SELECT * FROM a OUTER APPLY (SELECT * FROM b OUTER APPLY (SELECT * FROM c WHERE c.id = b.id) AS i) AS o',
     ['-|-|Lateral|outer|0|0|0', '-|-|Lateral|outer|0|0|0']),
    ('SELECT * FROM a INNER JOIN LATERAL (VALUES (1), (2)) AS v(n)',
     'SELECT * FROM a CROSS APPLY (VALUES (1), (2)) AS v(n)',
     ['-|-|Lateral|cross|0|0|0']),
    ('SELECT * FROM a INNER JOIN LATERAL b',
     'SELECT * FROM a CROSS APPLY b',
     ['-|-|Lateral|cross|0|0|0']),
    ('SELECT * FROM a JOIN b JOIN c JOIN d ON c.id = d.id ON b.id = c.id ON a.id = b.id',
     'SELECT * FROM a JOIN b JOIN c JOIN d ON c.id = d.id ON b.id = c.id ON a.id = b.id',
     ['-|-|Table|-|1|1|0', '-|-|Table|-|1|1|0', '-|-|Table|-|0|1|0']),
    ('SELECT * FROM a INNER JOIN LATERAL dbo.FN_TAGS(a.id) AS f JOIN b JOIN c ON b.id = c.id ON b.k = f.k',
     'SELECT * FROM a CROSS APPLY dbo.FN_TAGS(a.id) AS f JOIN b JOIN c ON b.id = c.id ON b.k = f.k',
     ['-|-|Lateral|cross|0|0|0', '-|-|Table|-|1|1|0', '-|-|Table|-|0|1|0']),
    ('SELECT * FROM a INNER JOIN b LEFT JOIN c ON c.id = b.id ON b.id = a.id LEFT JOIN LATERAL (SELECT * FROM d WHERE d.a_id = a.id LIMIT 1) AS x JOIN e JOIN f ON e.id = f.id ON e.id = x.id',
     'SELECT * FROM a INNER JOIN b LEFT JOIN c ON c.id = b.id ON b.id = a.id OUTER APPLY (SELECT TOP 1 * FROM d WHERE d.a_id = a.id) AS x JOIN e JOIN f ON e.id = f.id ON e.id = x.id',
     ['-|INNER|Table|-|1|1|0', 'LEFT|-|Table|-|0|1|0', '-|-|Lateral|outer|0|0|0', '-|-|Table|-|1|1|0', '-|-|Table|-|0|1|0']),
    ("SELECT * FROM a, b INNER JOIN LATERAL dbo.FN_SPLIT(b.tags, ',') AS s",
     "SELECT * FROM a, b CROSS APPLY dbo.FN_SPLIT(b.tags, ',') AS s",
     ['-|-|Table|-|0|0|0', '-|-|Lateral|cross|0|0|0']),
    ('SELECT * FROM a INNER JOIN LATERAL (SELECT 1, 2) AS t(x, y) LEFT JOIN LATERAL (SELECT * FROM b WHERE b.x = t.x LIMIT 1) AS u',
     'SELECT * FROM a CROSS APPLY (SELECT 1, 2) AS t(x, y) OUTER APPLY (SELECT TOP 1 * FROM b WHERE b.x = t.x) AS u',
     ['-|-|Lateral|cross|0|0|0', '-|-|Lateral|outer|0|0|0']),
    ('SELECT * FROM a LEFT JOIN b JOIN c USING (k) ON a.id = b.id',
     'SELECT * FROM a LEFT JOIN b JOIN c USING (k) ON a.id = b.id',
     ['LEFT|-|Table|-|1|1|0', '-|-|Table|-|0|0|1']),
    ('SELECT * FROM a INNER JOIN LATERAL (SELECT * FROM b JOIN c JOIN d ON c.id = d.id ON b.id = c.id WHERE b.a_id = a.id) AS x LEFT JOIN LATERAL dbo.FN_TAGS(x.id) AS t',
     'SELECT * FROM a CROSS APPLY (SELECT * FROM b JOIN c JOIN d ON c.id = d.id ON b.id = c.id WHERE b.a_id = a.id) AS x OUTER APPLY dbo.FN_TAGS(x.id) AS t',
     ['-|-|Lateral|cross|0|0|0', '-|-|Table|-|1|1|0', '-|-|Table|-|0|1|0', '-|-|Lateral|outer|0|0|0']),
    ("WITH s AS (SELECT * FROM a LEFT JOIN LATERAL (SELECT * FROM b WHERE b.a_id = a.id ORDER BY b.ts DESC LIMIT 1) AS x) SELECT * FROM s INNER JOIN LATERAL dbo.FN_SPLIT(s.tags, ',') AS t",
     "WITH s AS (SELECT * FROM a OUTER APPLY (SELECT TOP 1 * FROM b WHERE b.a_id = a.id ORDER BY b.ts DESC) AS x) SELECT * FROM s CROSS APPLY dbo.FN_SPLIT(s.tags, ',') AS t",
     ['-|-|Lateral|cross|0|0|0', '-|-|Lateral|outer|0|0|0']),
]


def _customer360(n, seed):
    spark, tsql, joins, cols = [], [], [], []
    for i in range(n):
        t = LOOKUPS[(i + seed) % len(LOOKUPS)]
        cross = (i + seed) % 3 == 0
        sel = ("SELECT %%s x.id AS %s_id, x.amount AS %s_amount, x.created_at AS %s_at FROM dbo.%s AS x "
               "WHERE x.customer_id = c.customer_id AND x.status <> 'void' ORDER BY x.created_at DESC" % (t, t, t, t))
        tsql.append("%s APPLY (%s) AS l%d" % ("CROSS" if cross else "OUTER", sel % "TOP 1", i))
        spark.append("%s JOIN LATERAL (%s LIMIT 1) AS l%d" % ("INNER" if cross else "LEFT", (sel % "").replace("SELECT  ", "SELECT "), i))
        joins.append(LATERAL_CROSS if cross else LATERAL_OUTER)
        cols.append("l%d.%s_amount" % (i, t))
    head = "SELECT c.customer_id, c.name, %s FROM dbo.customers AS c" % (", ".join(cols) or "1 AS one")
    tail = "WHERE c.region = 'EU'"
    return {"spark": " ".join([head] + spark + [tail]), "tsql": " ".join([head] + tsql + [tail]), "joins": joins}


def _event_enrichment(n, seed):
    spark, tsql, joins, cols = [], [], [], []
    for i in range(n):
        r = (i + seed) % 4
        fn = "dbo." + FUNCS[(i + seed) % len(FUNCS)].upper()
        if r == 2:
            dim = "LEFT JOIN dbo.%s AS d%d ON d%d.id = e.key_%d" % (DIMS[(i + seed) % len(DIMS)], i, i, i)
            tsql.append(dim)
            spark.append(dim)
            joins.append(DIM_JOIN)
            cols.append("d%d.name AS d%d_name" % (i, i))
            continue
        if r == 0:
            call_t, call_s, cross = "%s(e.attr_%d, N'v%d')" % (fn, i, seed), "%s(e.attr_%d, 'v%d')" % (fn, i, seed), True
        elif r == 1:
            call_t = call_s = "%s(e.event_id)" % fn
            cross = False
        else:
            call_t = call_s = "%s(e.session_id, %d)" % (fn, i)
            cross = False
        tsql.append("%s APPLY %s AS f%d" % ("CROSS" if cross else "OUTER", call_t, i))
        spark.append("%s JOIN LATERAL %s AS f%d" % ("INNER" if cross else "LEFT", call_s, i))
        joins.append(LATERAL_CROSS if cross else LATERAL_OUTER)
        cols.append("f%d.value AS f%d_value" % (i, i))
    head = "SELECT e.event_id, %s FROM dbo.events AS e" % (", ".join(cols) or "1 AS one")
    tail = "WHERE e.event_date >= '2024-01-01'"
    return {"spark": " ".join([head] + spark + [tail]), "tsql": " ".join([head] + tsql + [tail]), "joins": joins}


def expected(case, size, seed):
    if type(size) is not int or type(seed) is not int or not 0 <= seed < 1000000:
        raise ValueError("invalid size/seed")
    if case == "customer360" and 0 <= size <= 24:
        return _customer360(size, seed)
    if case == "event_enrichment" and 0 <= size <= 32:
        return _event_enrichment(size, seed)
    if case == "edge" and 0 <= size < len(EDGE_EXPECTED) and seed == 0:
        spark, tsql, joins = EDGE_EXPECTED[size]
        return {"spark": spark, "tsql": tsql, "joins": list(joins)}
    raise ValueError("unsupported case/size/seed")
