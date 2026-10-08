"""Author preflight worker. Native SQLGlot parse/qualify/generate, no timers."""

import argparse
import json


def make_input(size, seed):
    if type(size) is not int or not 1 <= size <= 24:
        raise ValueError("depth must be an integer between 1 and 24")
    if type(seed) is not int or not 0 <= seed < 1000000:
        raise ValueError("seed must be an integer between 0 and 999999")
    ctes = []
    for level in range(size):
        value = "NULL" if (level + seed) % 4 == 0 else f"'v{seed + level}'"
        attr = f"[STRUCT('k{level}' AS key, {value} AS value)]"
        if level == 0:
            body = f"SELECT id, {attr} AS attrs FROM orders"
        else:
            body = (
                f"SELECT a.id AS id, array_concat(a.attrs, {attr}) AS attrs "
                f"FROM c{level - 1} AS a JOIN orders AS o ON a.id = o.id"
            )
        ctes.append(f"c{level} AS ({body})")
    ctes.append(
        "filtered AS (SELECT id, ARRAY(SELECT x FROM UNNEST(attrs) AS x "
        f"WHERE NOT x.value IS NULL) AS attrs FROM c{size - 1})"
    )
    return "WITH " + ", ".join(ctes) + " SELECT * FROM filtered", {"orders": {"id": "INT64"}}


def run(case, size, seed):
    if case != "shared_unknown":
        raise ValueError("unsupported case")
    from sqlglot import parse_one
    from sqlglot.optimizer.qualify import qualify

    sql, schema = make_input(size, seed)
    result = qualify(parse_one(sql, dialect="bigquery"), schema=schema, dialect="bigquery", identify=False)
    return {"sql": result.sql(dialect="bigquery")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
