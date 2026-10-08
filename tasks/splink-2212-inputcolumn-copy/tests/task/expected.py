"""Protected golden-baseline oracle. Standard library only; never imports splink or the workload.

expected(case, size, seed) returns, for exactly the declared (case, size, seed) rows, the dict that
workload.run returned on the PINNED BASE tree (splink ee88655a) inside the Linux agent image
(python 3.12, duckdb 1.0.0, sqlglot 25.9.0, PYTHONHASHSEED=0, DuckDB threads=1). Receipt:
mining/splink-2212-inputcolumn-copy/sizing/golden-baseline-r07.json (sha256 239f6d0ce3b74af106157add886e7e84899eba55c2046e91d64c0006411dd197),
workload.py sha256 61d8e31d66985176a79a2029b91b549534087199c0d55621707a473c6fb5a99f. The public reference (7b70d6b5), the alternative and the naive control
produced byte-identical results for every row (golden-*-r07.json).

This is a frozen behavioral reference, not an independent re-implementation of Fellegi-Sunter scoring:
it pins the exact candidate sets, match weights (6 dp) and compare_two_records weights per lookup.
Any undeclared (case, size, seed) raises, so the verifier cannot silently accept unknown rows.
"""
import json

_TABLE = json.loads(r'''{
 "lookup|24|31337": {
  "candidate_counts": [
   1,
   2,
   2,
   1,
   1,
   1,
   1,
   1,
   2,
   2,
   1,
   2,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0,
   0
  ],
  "case": "lookup",
  "compared": 12,
  "lookups": 24,
  "raw": null,
  "seed": 31337,
  "sha256": "7a9397a2d0fd0a7667d926a7314eac13ed5626ae73b3bddea48b5894c6044a16",
  "size": 24
 },
 "lookup|2|7": {
  "candidate_counts": [
   2,
   0
  ],
  "case": "lookup",
  "compared": 1,
  "lookups": 2,
  "raw": [
   {
    "candidates": [
     [
      4731,
      61.243524
     ],
     [
      6761,
      54.806933
     ]
    ],
    "compared": [
     4731,
     61.243524
    ]
   },
   {
    "candidates": [],
    "compared": null
   }
  ],
  "seed": 7,
  "sha256": "8c57b4dbb1b39dd67ef6178954d15cd18e445aee27785eb4331d6d93e3c5356b",
  "size": 2
 },
 "mixed_rules|3|5": {
  "candidate_counts": [
   0,
   1,
   0
  ],
  "case": "mixed_rules",
  "compared": 1,
  "lookups": 3,
  "raw": [
   {
    "candidates": [],
    "compared": null
   },
   {
    "candidates": [
     [
      8357,
      50.289879
     ]
    ],
    "compared": [
     8357,
     50.289879
    ]
   },
   {
    "candidates": [],
    "compared": null
   }
  ],
  "seed": 5,
  "sha256": "90ab63b9756eac72846ca6434076b88a224217e0c1110d08f9cad2a02d7a06d4",
  "size": 3
 },
 "mixed_rules|4|777": {
  "candidate_counts": [
   0,
   2,
   0,
   0
  ],
  "case": "mixed_rules",
  "compared": 1,
  "lookups": 4,
  "raw": [
   {
    "candidates": [],
    "compared": null
   },
   {
    "candidates": [
     [
      2082,
      44.04386
     ],
     [
      5104,
      44.04386
     ]
    ],
    "compared": [
     2082,
     44.04386
    ]
   },
   {
    "candidates": [],
    "compared": null
   },
   {
    "candidates": [],
    "compared": null
   }
  ],
  "seed": 777,
  "sha256": "8e5c3aad483b04d05b32b773f4a8bd6b45c47960fce5c19f635375ad7d232076",
  "size": 4
 },
 "resubmit|4|9001": {
  "candidate_counts": [
   2,
   1,
   1,
   1
  ],
  "case": "resubmit",
  "compared": 4,
  "lookups": 4,
  "raw": [
   {
    "candidates": [
     [
      4428,
      61.802332
     ],
     [
      8496,
      58.090444
     ]
    ],
    "compared": [
     4428,
     61.802332
    ]
   },
   {
    "candidates": [
     [
      11736,
      67.772155
     ]
    ],
    "compared": [
     11736,
     67.772155
    ]
   },
   {
    "candidates": [
     [
      10769,
      61.168754
     ]
    ],
    "compared": [
     10769,
     61.168754
    ]
   },
   {
    "candidates": [
     [
      5041,
      65.076343
     ]
    ],
    "compared": [
     5041,
     65.076343
    ]
   }
  ],
  "seed": 9001,
  "sha256": "56de24cd5e000f9a066d45eb6908bfa27ead0b61b3cb3de834a07f47bbe5d43a",
  "size": 4
 }
}''')


def expected(case, size, seed):
    key = f"{case}|{size}|{seed}"
    if key not in _TABLE:
        raise ValueError("Undeclared case/size/seed: " + key)
    return json.loads(json.dumps(_TABLE[key]))
