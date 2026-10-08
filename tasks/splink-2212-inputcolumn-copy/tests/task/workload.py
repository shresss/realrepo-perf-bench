"""Real-time record lookup service on splink 3 (DuckDB backend). Real public API; no timing, reward or answers here.

A person register of 13,000 records (10,000 people plus 30% planted near-duplicates, generated from a fixed
seed exactly like the trained service's register) is loaded into an in-memory DuckDB (threads=1) together
with a pre-trained Fellegi-Sunter model (MODEL_JSON below: 7 comparisons with term-frequency adjustments,
trained on the same register). Term-frequency tables for first_name, surname and city are precomputed once.
Then `size` incoming records are scored one at a time, as an online matching endpoint would:

  linker.find_matches_to_new_records([record], blocking_rules=..., match_weight_threshold=-4)
  linker.compare_two_records(record, best_candidate)          # only when a candidate exists

Cases (the seed picks which incoming records arrive):
  lookup         half the incoming records are register people re-submitted with one field edited
                 (first_name/email/postcode get a trailing character changed, city goes missing),
                 half come from an independent register; blocking on surname or dob.
  resubmit       every incoming record is an edited re-submission of a register person.
  mixed_rules    every incoming record is an edited re-submission whose surname and date of birth were also
                 mistyped, and consecutive lookups use different blocking rule sets (surname/dob, then
                 postcode/email/first_name+city, then dob only), so each lookup must honor its own rules.

Observables: per-lookup candidate counts, the candidate rows (other unique_id, match_weight rounded to
6 dp) and compare_two_records match weights, digested with sha256; raw rows are returned for size <= 4.
"""
import datetime
import hashlib
import json

SMALL = 4
REGISTER_PEOPLE, REGISTER_SEED, DUP_FRAC = 10_000, 2212, 0.3
RULES = {
    "default": ["l.surname = r.surname", "l.dob = r.dob"],
    "contact": ["l.postcode = r.postcode", "l.email = r.email", "l.first_name = r.first_name and l.city = r.city"],
    "dob": ["l.dob = r.dob"],
}
MODEL_JSON = '{"blocking_rules_to_generate_predictions":[{"blocking_rule":"l.\\"surname\\" = r.\\"surname\\"","sql_dialect":"duckdb"},{"blocking_rule":"l.\\"dob\\" = r.\\"dob\\"","sql_dialect":"duckdb"},{"blocking_rule":"(l.\\"city\\" = r.\\"city\\") AND (l.\\"first_name\\" = r.\\"first_name\\")","sql_dialect":"duckdb"}],"comparisons":[{"comparison_description":"Exact match vs. First_Name within levenshtein threshold 1 vs. First_Name within damerau-levenshtein threshold 1 vs. First_Name within jaro_winkler thresholds 0.9, 0.8 vs. anything else","comparison_levels":[{"is_null_level":true,"label_for_charts":"Null","sql_condition":"\\"first_name_l\\" IS NULL OR \\"first_name_r\\" IS NULL"},{"label_for_charts":"Exact match first_name","m_probability":0.8134387351781595,"sql_condition":"\\"first_name_l\\" = \\"first_name_r\\"","tf_adjustment_column":"first_name","tf_adjustment_weight":1.0,"u_probability":0.0023398494746516307},{"label_for_charts":"Damerau_levenshtein <= 1","m_probability":0.18656126482184046,"sql_condition":"damerau_levenshtein(\\"first_name_l\\", \\"first_name_r\\") <= 1","u_probability":0.05892843836160858},{"label_for_charts":"Jaro_winkler_similarity >= 0.9","m_probability":9.057452569865333e-26,"sql_condition":"jaro_winkler_similarity(\\"first_name_l\\", \\"first_name_r\\") >= 0.9","u_probability":0.028684269355920416},{"label_for_charts":"Jaro_winkler_similarity >= 0.8","m_probability":2.047724326618559e-25,"sql_condition":"jaro_winkler_similarity(\\"first_name_l\\", \\"first_name_r\\") >= 0.8","u_probability":0.2760227526764202},{"label_for_charts":"All other comparisons","m_probability":1.4222972009124714e-19,"sql_condition":"ELSE","u_probability":0.6340246901313992}],"output_column_name":"first_name"},{"comparison_description":"Exact match vs. Surname within levenshtein threshold 1 vs. Surname within damerau-levenshtein threshold 1 vs. Surname within jaro_winkler thresholds 0.9, 0.8 vs. anything else","comparison_levels":[{"is_null_level":true,"label_for_charts":"Null","sql_condition":"\\"surname_l\\" IS NULL OR \\"surname_r\\" IS NULL"},{"label_for_charts":"Exact match surname","m_probability":0.9031620553363532,"sql_condition":"\\"surname_l\\" = \\"surname_r\\"","tf_adjustment_column":"surname","tf_adjustment_weight":1.0,"u_probability":0.0008445316575175737},{"label_for_charts":"Damerau_levenshtein <= 1","m_probability":0.09683794466364684,"sql_condition":"damerau_levenshtein(\\"surname_l\\", \\"surname_r\\") <= 1","u_probability":0.02412876623860503},{"label_for_charts":"Jaro_winkler_similarity >= 0.9","m_probability":7.983793976803101e-27,"sql_condition":"jaro_winkler_similarity(\\"surname_l\\", \\"surname_r\\") >= 0.9","u_probability":0.014888596338706874},{"label_for_charts":"Jaro_winkler_similarity >= 0.8","m_probability":6.473747341442136e-27,"sql_condition":"jaro_winkler_similarity(\\"surname_l\\", \\"surname_r\\") >= 0.8","u_probability":0.1729600834595991},{"label_for_charts":"All other comparisons","m_probability":3.9583409440923846e-19,"sql_condition":"ELSE","u_probability":0.7871780223055714}],"output_column_name":"surname"},{"comparison_description":"Exact match vs. Dob within damerau-levenshtein threshold 1 vs. Dates within the following thresholds Month(s): 1, Year(s): 1, Year(s): 10 vs. anything else","comparison_levels":[{"is_null_level":true,"label_for_charts":"Null","sql_condition":"\\"dob_l\\" IS NULL OR \\"dob_r\\" IS NULL"},{"label_for_charts":"Exact match","m_probability":0.841320072332903,"sql_condition":"\\"dob_l\\" = \\"dob_r\\"","u_probability":6.458183263369681e-05},{"label_for_charts":"Damerau_levenshtein <= 1","m_probability":0.019439421338088368,"sql_condition":"damerau_levenshtein(\\"dob_l\\", \\"dob_r\\") <= 1","u_probability":0.0014804143172955115},{"label_for_charts":"Within 1 month","m_probability":0.13517179023499729,"sql_condition":"\\n            abs(date_diff(\'month\',\\n                strptime(\\"dob_l\\", \'%Y-%m-%d\'),\\n                strptime(\\"dob_r\\", \'%Y-%m-%d\'))\\n                ) <= 1\\n        ","u_probability":0.003601679127648476},{"label_for_charts":"Within 1 year","m_probability":0.00406871609401131,"sql_condition":"\\n            abs(date_diff(\'year\',\\n                strptime(\\"dob_l\\", \'%Y-%m-%d\'),\\n                strptime(\\"dob_r\\", \'%Y-%m-%d\'))\\n                ) <= 1\\n        ","u_probability":0.04486450234730122},{"label_for_charts":"Within 10 years","m_probability":1.1245753014875398e-112,"sql_condition":"\\n            abs(date_diff(\'year\',\\n                strptime(\\"dob_l\\", \'%Y-%m-%d\'),\\n                strptime(\\"dob_r\\", \'%Y-%m-%d\'))\\n                ) <= 10\\n        ","u_probability":0.2662361211157754},{"label_for_charts":"All other comparisons","m_probability":9.317387190882972e-119,"sql_condition":"ELSE","u_probability":0.6837527012593457}],"output_column_name":"dob"},{"comparison_description":"Exact match vs. anything else","comparison_levels":[{"is_null_level":true,"label_for_charts":"Null","sql_condition":"\\"city_l\\" IS NULL OR \\"city_r\\" IS NULL"},{"label_for_charts":"Exact match","m_probability":1.0,"sql_condition":"\\"city_l\\" = \\"city_r\\"","tf_adjustment_column":"city","tf_adjustment_weight":1.0,"u_probability":0.016789803169589983},{"label_for_charts":"All other comparisons","m_probability":2.8182023538090117e-21,"sql_condition":"ELSE","u_probability":0.98321019683041}],"output_column_name":"city"},{"comparison_description":"Exact match on full postcode vs. exact match on sector vs. exact match on district vs. exact match on area vs. all other comparisons","comparison_levels":[{"is_null_level":true,"label_for_charts":"Null","sql_condition":"\\"postcode_l\\" IS NULL OR \\"postcode_r\\" IS NULL"},{"label_for_charts":"Exact match postcode","m_probability":0.8137058731033204,"sql_condition":"lower(\\"postcode_l\\") = lower(\\"postcode_r\\")","u_probability":3.9742666236121115e-05},{"label_for_charts":"Exact match Postcode Sector","m_probability":0.1862941268966794,"sql_condition":"\\n        regexp_extract(lower(\\"postcode_l\\"), \'^[A-Za-z]{1,2}[0-9][A-Za-z0-9]? [0-9]\')\\n     = \\n        regexp_extract(lower(\\"postcode_r\\"), \'^[A-Za-z]{1,2}[0-9][A-Za-z0-9]? [0-9]\')\\n    ","u_probability":0.00011922799870836335},{"label_for_charts":"Exact match Postcode District","m_probability":1.0515436359011028e-27,"sql_condition":"\\n        regexp_extract(lower(\\"postcode_l\\"), \'^[A-Za-z]{1,2}[0-9][A-Za-z0-9]?\')\\n     = \\n        regexp_extract(lower(\\"postcode_r\\"), \'^[A-Za-z]{1,2}[0-9][A-Za-z0-9]?\')\\n    ","u_probability":0.001535060483370178},{"label_for_charts":"Exact match Postcode Area","m_probability":5.908689760038925e-28,"sql_condition":"\\n        regexp_extract(lower(\\"postcode_l\\"), \'^[A-Za-z]{1,2}\')\\n     = \\n        regexp_extract(lower(\\"postcode_r\\"), \'^[A-Za-z]{1,2}\')\\n    ","u_probability":0.04791971981420304},{"label_for_charts":"All other comparisons","m_probability":2.714850094124906e-19,"sql_condition":"ELSE","u_probability":0.9503862490374823}],"output_column_name":"postcode"},{"comparison_description":"Exact match vs. Exact username match different domain vs. Fuzzy Email within jaro_winkler threshold 0.88 vs. Fuzzy Username within jaro_winkler threshold 0.88 vs. anything else","comparison_levels":[{"is_null_level":true,"label_for_charts":"Null","sql_condition":"\\"email_l\\" IS NULL OR \\"email_r\\" IS NULL"},{"label_for_charts":"Exact match email","m_probability":0.5726436469419367,"sql_condition":"\\"email_l\\" = \\"email_r\\"","u_probability":1.9871333118060558e-05},{"label_for_charts":"Exact match email","m_probability":0.4273563530580632,"sql_condition":"\\n        regexp_extract(\\"email_l\\", \'^[^@]+\')\\n     = \\n        regexp_extract(\\"email_r\\", \'^[^@]+\')\\n    ","u_probability":1.9871333118060558e-05},{"label_for_charts":"Jaro_winkler_similarity email >= 0.88","m_probability":2.0123465434662697e-19,"sql_condition":"jaro_winkler_similarity(\\"email_l\\", \\"email_r\\") >= 0.88","u_probability":0.2174569661442162},{"label_for_charts":"Jaro_winkler_similarity Username >= 0.88","sql_condition":"jaro_winkler_similarity(\\n        regexp_extract(\\"email_l\\", \'^[^@]+\')\\n    , \\n        regexp_extract(\\"email_r\\", \'^[^@]+\')\\n    ) >= 0.88","u_probability":0.0003775553292431506},{"label_for_charts":"All other comparisons","m_probability":1.4050100732309402e-19,"sql_condition":"ELSE","u_probability":0.7821257358603045}],"output_column_name":"email"},{"comparison_description":"Exact match vs. Phone within levenshtein thresholds 1, 2 vs. anything else","comparison_levels":[{"is_null_level":true,"label_for_charts":"Null","sql_condition":"\\"phone_l\\" IS NULL OR \\"phone_r\\" IS NULL"},{"label_for_charts":"Exact match","m_probability":1.0,"sql_condition":"\\"phone_l\\" = \\"phone_r\\"","u_probability":1.1204293485263552e-05},{"label_for_charts":"Levenshtein <= 1","sql_condition":"levenshtein(\\"phone_l\\", \\"phone_r\\") <= 1"},{"label_for_charts":"Levenshtein <= 2","sql_condition":"levenshtein(\\"phone_l\\", \\"phone_r\\") <= 2","u_probability":5.602146742631776e-06},{"label_for_charts":"All other comparisons","m_probability":7.23018082165529e-22,"sql_condition":"ELSE","u_probability":0.999983193559772}],"output_column_name":"phone"}],"link_type":"dedupe_only","linker_uid":"ecqw3ze2","probability_two_random_records_match":3.1464804139625285e-05,"retain_intermediate_calculation_columns":true,"retain_matching_columns":true,"sql_dialect":"duckdb","unique_id_column_name":"unique_id"}'


def make_people(n, seed, dup_frac):
    """Seeded synthetic person register with planted near-duplicates (same generator as the service fixture)."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    first = np.array([f"fn{i}" for i in range(max(50, n // 25))])
    sur = np.array([f"sn{i}" for i in range(max(100, n // 8))])
    areas = ["SW", "SE", "N", "NW", "E", "W", "EC", "WC", "B", "M", "L", "LS", "S", "BS", "CF", "EH", "G", "NE", "CB", "OX"]
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    cities = np.array([f"city{i}" for i in range(60)])
    df = pd.DataFrame({"first_name": rng.choice(first, n), "surname": rng.choice(sur, n),
                       "dob": (np.datetime64("1940-01-01") + rng.integers(0, 365 * 60, n)).astype(str),
                       "city": rng.choice(cities, n),
                       "postcode": [f"{areas[a]}{d} {s}{letters[u1]}{letters[u2]}" for a, d, s, u1, u2 in
                                    zip(rng.integers(0, 20, n), rng.integers(1, 30, n), rng.integers(0, 10, n),
                                        rng.integers(0, 26, n), rng.integers(0, 26, n))]})
    df["email"] = df.first_name + "." + df.surname + rng.integers(0, 50, n).astype(str) + "@ex.org"
    df["phone"] = [f"07{x:09d}" for x in rng.integers(0, 10**9, n)]
    dups = df.sample(frac=dup_frac, random_state=seed).copy()
    for col, p in (("first_name", 0.2), ("surname", 0.1), ("dob", 0.15), ("city", 0.3), ("postcode", 0.2),
                   ("email", 0.4), ("phone", 0.3)):
        mask = rng.random(len(dups)) < p
        if col in ("city", "phone"):
            dups.loc[mask, col] = None
        elif col == "dob":
            shifted = pd.to_datetime(dups.loc[mask, col]) + pd.to_timedelta(rng.integers(1, 40, int(mask.sum())), unit="D")
            dups.loc[mask, col] = shifted.dt.strftime("%Y-%m-%d")
        else:
            dups.loc[mask, col] = dups.loc[mask, col].astype(str).str[:-1] + ("X" if col == "postcode" else "x")
    df = pd.concat([df, dups], ignore_index=True)
    df = df.sample(frac=1.0, random_state=seed + 1).reset_index(drop=True)
    df["unique_id"] = np.arange(len(df))
    return df


def _clean(record):
    import pandas as pd
    return {k: (None if pd.isna(v) else v) for k, v in record.items()}


def incoming_records(df, case, size, seed):
    import pandas as pd
    resubmitted = size if case in ("resubmit", "mixed_rules") else size // 2
    src = df.sample(n=resubmitted, random_state=seed).copy()
    fields = ["first_name", "email", "city", "postcode"]
    for i, idx in enumerate(src.index):
        field = fields[i % 4]
        value = src.at[idx, field]
        src.at[idx, field] = None if field == "city" else (None if value is None else str(value)[:-1] + "Q")
        if case == "mixed_rules":
            src.at[idx, "surname"] = str(src.at[idx, "surname"]) + "Q"
            dob = datetime.date.fromisoformat(str(src.at[idx, "dob"]))
            src.at[idx, "dob"] = (dob + datetime.timedelta(days=3 + i % 5)).isoformat()
    parts = [src]
    if size - resubmitted:
        parts.append(make_people(2000, seed, DUP_FRAC).head(size - resubmitted))
    inc = pd.concat(parts, ignore_index=True)
    records = [_clean(r) for r in inc.drop(columns=["unique_id"]).to_dict("records")]
    for i, r in enumerate(records):
        r["unique_id"] = 10_000_000 + i
    return records


def run(case, size, seed):
    if case not in ("lookup", "resubmit", "mixed_rules") or not 1 <= size <= 200 or not 0 <= seed <= 99_999:
        raise ValueError("Unsupported case/size/seed")
    import duckdb
    from splink.duckdb.linker import DuckDBLinker

    df = make_people(REGISTER_PEOPLE, REGISTER_SEED, DUP_FRAC)
    records = incoming_records(df, case, size, seed)
    con = duckdb.connect(config={"threads": 1})
    linker = DuckDBLinker(df, connection=con)
    linker.load_model(json.loads(MODEL_JSON))
    for column in ("first_name", "surname", "city"):
        linker.compute_tf_table(column)
    by_id = df.set_index("unique_id")
    order = ("default", "contact", "dob")
    counts, lookups = [], []
    for i, record in enumerate(records):
        rules = RULES[order[i % 3] if case == "mixed_rules" else "default"]
        found = linker.find_matches_to_new_records([record], blocking_rules=rules,
                                                   match_weight_threshold=-4).as_pandas_dataframe()
        rows = sorted((int(x.unique_id_l if x.unique_id_r == record["unique_id"] else x.unique_id_r),
                       round(float(x.match_weight), 6)) for x in found.itertuples())
        compared = None
        if rows:
            best = max(rows, key=lambda t: (t[1], -t[0]))[0]
            other = _clean(by_id.loc[best].to_dict())
            other["unique_id"] = best
            cmp = linker.compare_two_records(record, other).as_pandas_dataframe()
            compared = [best, round(float(cmp.match_weight.iloc[0]), 6)]
        counts.append(len(rows))
        lookups.append({"candidates": [list(r) for r in rows], "compared": compared})
    canonical = json.dumps(lookups, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"case": case, "size": size, "seed": seed, "lookups": len(records), "candidate_counts": counts,
            "compared": sum(1 for x in lookups if x["compared"] is not None),
            "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "raw": lookups if size <= SMALL else None}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
