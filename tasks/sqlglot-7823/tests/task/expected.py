"""Independent stdlib-only grammar oracle; does not import workload or SQLGlot.

This preserves the public API's canonical SQL string as well as the relational
meaning. DuckDB execution is a supplementary independent engine check.
"""


def expected(case, size, seed):
    if case == "shared_known":
        return expected_known(size, seed)
    if case != "shared_unknown":
        raise ValueError("unsupported case")
    if type(size) is not int or not 1 <= size <= 24:
        raise ValueError("invalid depth")
    if type(seed) is not int or not 0 <= seed < 1000000:
        raise ValueError("invalid seed")
    parts = []
    for k in range(size):
        literal = "NULL" if (seed + k) % 4 == 0 else "'v" + str(seed + k) + "'"
        struct = "[STRUCT('k" + str(k) + "' AS key, " + literal + " AS value)]"
        if k:
            select = (
                "SELECT a.id AS id, array_concat(a.attrs, " + struct + ") AS attrs FROM c"
                + str(k - 1) + " AS a JOIN orders AS o ON a.id = o.id"
            )
        else:
            select = "SELECT orders.id AS id, " + struct + " AS attrs FROM orders AS orders"
        parts.append("c" + str(k) + " AS (" + select + ")")
    last = "c" + str(size - 1)
    parts.append(
        "filtered AS (SELECT " + last + ".id AS id, ARRAY(SELECT x AS x FROM UNNEST("
        + last + ".attrs) AS x WHERE NOT x.value IS NULL) AS attrs FROM " + last + " AS " + last + ")"
    )
    return {"sql": "WITH " + ", ".join(parts) + " SELECT filtered.id AS id, filtered.attrs AS attrs FROM filtered AS filtered"}


def expected_known(size, seed):
    """Upstream output for the known-type chain: the qualifier resolves the unqualified struct fields
    through the traced ARRAY<STRUCT<key, value>> type (it validates them and leaves them unqualified);
    if the type is lost, qualification raises 'Column ... could not be resolved' instead."""
    if type(size) is not int or not 1 <= size <= 24:
        raise ValueError("invalid depth")
    if type(seed) is not int or not 0 <= seed < 1000000:
        raise ValueError("invalid seed")
    parts = ["c0 AS (SELECT orders.id AS id, orders.attrs AS attrs FROM orders AS orders)"]
    for k in range(1, size):
        parts.append(
            "c" + str(k) + " AS (SELECT a.id AS id, a.attrs AS attrs FROM c" + str(k - 1)
            + " AS a JOIN orders AS o ON a.id = o.id)"
        )
    last = "c" + str(size - 1)
    return {"sql": "WITH " + ", ".join(parts) + " SELECT " + last + ".id AS id, ARRAY(SELECT x AS x FROM UNNEST("
            + last + ".attrs) AS x WHERE NOT value IS NULL AND key <> 'k" + str(seed) + "') AS vals FROM "
            + last + " AS " + last}


def expected_rows(size, seed):
    attributes = [{"key": f"k{k}", "value": f"v{seed + k}"} for k in range(size) if (seed + k) % 4]
    return [[i, attributes] for i in [1, 2, 3]]
