"""Protected oracle for iceberg-2674-summary-metadata-hoist. Standard library only; never imports pyiceberg.

Golden observables recorded from the UNTOUCHED base tree (d3eb149f) inside the Linux task image with the pinned lock,
and cross-checked byte-identical on the reference tree (1f9c46b4) and the alternative control. They encode the
behavior a performance change must preserve: snapshot operations and full summaries (including Parquet file sizes,
which are deterministic for the pinned pyarrow), parent linkage, snapshot counts, schema, properties and added files.
"""
import json

_GOLDEN = json.loads(r'''
{
 "backfill|500|11": {
  "added_files": null,
  "added_files_count": 480,
  "added_files_sha256": "c4a4e8eb9a35882f984896f30101fe17289d380867c422328c7e1e013314716e",
  "case": "backfill",
  "properties": {},
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 11,
  "size": 500,
  "snapshots": 502,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "480",
     "added-files-size": "3815017",
     "added-records": "120000",
     "changed-partition-count": "480",
     "total-data-files": "5480",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "499370950"
    }
   }
  ]
 },
 "empty-table|0|0": {
  "added_files": [],
  "added_files_count": 0,
  "added_files_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
  "case": "empty-table",
  "properties": {
   "commit.manifest-merge.enabled": "true"
  },
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 0,
  "size": 0,
  "snapshots": 2,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "2",
     "added-files-size": "4338",
     "added-records": "10",
     "changed-partition-count": "2",
     "total-data-files": "2",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-files-size": "4338",
     "total-position-deletes": "0",
     "total-records": "10"
    }
   },
   {
    "operation": "Operation.DELETE",
    "parent_is_previous_current": true,
    "summary": {
     "changed-partition-count": "1",
     "deleted-data-files": "1",
     "deleted-records": "5",
     "removed-files-size": "2169",
     "total-data-files": "1",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-files-size": "2169",
     "total-position-deletes": "0",
     "total-records": "5"
    }
   }
  ]
 },
 "fast-small|10|0": {
  "added_files": [
   [
    "eu-central",
    20604,
    20
   ],
   [
    "eu-central",
    20605,
    20
   ],
   [
    "us-east",
    20604,
    20
   ],
   [
    "us-east",
    20605,
    20
   ],
   [
    "us-west",
    20604,
    20
   ],
   [
    "us-west",
    20605,
    20
   ]
  ],
  "added_files_count": 6,
  "added_files_sha256": "b0c114a5f3dc036da68bfc75ef1be84b6acabc763f5a0a16933e9d1e198482f5",
  "case": "fast-small",
  "properties": {},
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 0,
  "size": 10,
  "snapshots": 12,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "6",
     "added-files-size": "15395",
     "added-records": "120",
     "changed-partition-count": "6",
     "total-data-files": "106",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "10426405"
    }
   }
  ]
 },
 "fast-small|25|3": {
  "added_files": [
   [
    "eu-central",
    20604,
    20
   ],
   [
    "eu-central",
    20605,
    20
   ],
   [
    "us-east",
    20604,
    20
   ],
   [
    "us-east",
    20605,
    20
   ],
   [
    "us-west",
    20604,
    20
   ],
   [
    "us-west",
    20605,
    20
   ]
  ],
  "added_files_count": 6,
  "added_files_sha256": "b0c114a5f3dc036da68bfc75ef1be84b6acabc763f5a0a16933e9d1e198482f5",
  "case": "fast-small",
  "properties": {},
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 3,
  "size": 25,
  "snapshots": 27,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "6",
     "added-files-size": "15411",
     "added-records": "120",
     "changed-partition-count": "6",
     "total-data-files": "256",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "23803555"
    }
   }
  ]
 },
 "merge-append-delete|10|0": {
  "added_files": [],
  "added_files_count": 0,
  "added_files_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
  "case": "merge-append-delete",
  "properties": {
   "commit.manifest-merge.enabled": "true"
  },
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 0,
  "size": 10,
  "snapshots": 13,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "6",
     "added-files-size": "15395",
     "added-records": "120",
     "changed-partition-count": "6",
     "total-data-files": "106",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "10426405"
    }
   },
   {
    "operation": "Operation.DELETE",
    "parent_is_previous_current": true,
    "summary": {
     "changed-partition-count": "3",
     "deleted-data-files": "11",
     "deleted-records": "971507",
     "removed-files-size": "35964515",
     "total-data-files": "95",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "9454898"
    }
   }
  ]
 },
 "merge-delete-none|10|0": {
  "added_files": [
   [
    "eu-central",
    20604,
    20
   ],
   [
    "eu-central",
    20605,
    20
   ],
   [
    "us-east",
    20604,
    20
   ],
   [
    "us-east",
    20605,
    20
   ],
   [
    "us-west",
    20604,
    20
   ],
   [
    "us-west",
    20605,
    20
   ]
  ],
  "added_files_count": 6,
  "added_files_sha256": "b0c114a5f3dc036da68bfc75ef1be84b6acabc763f5a0a16933e9d1e198482f5",
  "case": "merge-delete-none",
  "properties": {
   "commit.manifest-merge.enabled": "true"
  },
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 0,
  "size": 10,
  "snapshots": 12,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "6",
     "added-files-size": "15395",
     "added-records": "120",
     "changed-partition-count": "6",
     "total-data-files": "106",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "10426405"
    }
   },
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": false,
    "summary": {
     "added-data-files": "6",
     "added-files-size": "15395",
     "added-records": "120",
     "changed-partition-count": "6",
     "total-data-files": "106",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "10426405"
    }
   }
  ]
 },
 "reload|1000|0": {
  "added_files": null,
  "added_files_count": 240,
  "added_files_sha256": "928ee356e63da2d8e4d6a76eda8d770a8cee2a3dfe5115cc5cdf5cac51ad9878",
  "case": "reload",
  "properties": {},
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 0,
  "size": 1000,
  "snapshots": 1002,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "240",
     "added-files-size": "6191073",
     "added-records": "240000",
     "changed-partition-count": "240",
     "total-data-files": "10240",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "1000870929"
    }
   }
  ]
 },
 "tx-props-then-append|10|0": {
  "added_files": [
   [
    "eu-central",
    20604,
    20
   ],
   [
    "eu-central",
    20605,
    20
   ],
   [
    "us-east",
    20604,
    20
   ],
   [
    "us-east",
    20605,
    20
   ],
   [
    "us-west",
    20604,
    20
   ],
   [
    "us-west",
    20605,
    20
   ]
  ],
  "added_files_count": 6,
  "added_files_sha256": "b0c114a5f3dc036da68bfc75ef1be84b6acabc763f5a0a16933e9d1e198482f5",
  "case": "tx-props-then-append",
  "properties": {
   "write.summary.partition-limit": "100"
  },
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 0,
  "size": 10,
  "snapshots": 12,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "6",
     "added-files-size": "15395",
     "added-records": "120",
     "changed-partition-count": "6",
     "partition-summaries-included": "true",
     "partitions.region=eu-central/event_date=2026-05-31": "added-files-size=2576,added-data-files=1,added-records=20",
     "partitions.region=eu-central/event_date=2026-06-01": "added-files-size=2570,added-data-files=1,added-records=20",
     "partitions.region=us-east/event_date=2026-05-31": "added-files-size=2561,added-data-files=1,added-records=20",
     "partitions.region=us-east/event_date=2026-06-01": "added-files-size=2564,added-data-files=1,added-records=20",
     "partitions.region=us-west/event_date=2026-05-31": "added-files-size=2563,added-data-files=1,added-records=20",
     "partitions.region=us-west/event_date=2026-06-01": "added-files-size=2561,added-data-files=1,added-records=20",
     "total-data-files": "106",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "10426405"
    }
   }
  ]
 },
 "tx-schema-then-append|10|0": {
  "added_files": [
   [
    "eu-central",
    20604,
    20
   ],
   [
    "eu-central",
    20605,
    20
   ],
   [
    "us-east",
    20604,
    20
   ],
   [
    "us-east",
    20605,
    20
   ],
   [
    "us-west",
    20604,
    20
   ],
   [
    "us-west",
    20605,
    20
   ]
  ],
  "added_files_count": 6,
  "added_files_sha256": "b0c114a5f3dc036da68bfc75ef1be84b6acabc763f5a0a16933e9d1e198482f5",
  "case": "tx-schema-then-append",
  "properties": {},
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5",
   "channel"
  ],
  "seed": 0,
  "size": 10,
  "snapshots": 12,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "6",
     "added-files-size": "17369",
     "added-records": "120",
     "changed-partition-count": "6",
     "total-data-files": "106",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "10426405"
    }
   }
  ]
 },
 "tx-two-appends|10|0": {
  "added_files": [
   [
    "eu-central",
    20605,
    20
   ],
   [
    "us-east",
    20605,
    20
   ],
   [
    "us-west",
    20605,
    20
   ]
  ],
  "added_files_count": 3,
  "added_files_sha256": "a6e4443421d32429b392e22acd8dabe1467e75330e0a267c03c7e73364c03748",
  "case": "tx-two-appends",
  "properties": {},
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 0,
  "size": 10,
  "snapshots": 13,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "3",
     "added-files-size": "7700",
     "added-records": "60",
     "changed-partition-count": "3",
     "total-data-files": "103",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "10426345"
    }
   },
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "3",
     "added-files-size": "7695",
     "added-records": "60",
     "changed-partition-count": "3",
     "total-data-files": "106",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "10426405"
    }
   }
  ]
 },
 "tx-two-appends|25|5": {
  "added_files": [
   [
    "eu-central",
    20605,
    20
   ],
   [
    "us-east",
    20605,
    20
   ],
   [
    "us-west",
    20605,
    20
   ]
  ],
  "added_files_count": 3,
  "added_files_sha256": "a6e4443421d32429b392e22acd8dabe1467e75330e0a267c03c7e73364c03748",
  "case": "tx-two-appends",
  "properties": {},
  "schema_fields": [
   "event_id",
   "event_ts",
   "region",
   "event_date",
   "c5"
  ],
  "seed": 5,
  "size": 25,
  "snapshots": 28,
  "steps": [
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "3",
     "added-files-size": "7699",
     "added-records": "60",
     "changed-partition-count": "3",
     "total-data-files": "253",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "26404129"
    }
   },
   {
    "operation": "Operation.APPEND",
    "parent_is_previous_current": true,
    "summary": {
     "added-data-files": "3",
     "added-files-size": "7699",
     "added-records": "60",
     "changed-partition-count": "3",
     "total-data-files": "256",
     "total-delete-files": "0",
     "total-equality-deletes": "0",
     "total-position-deletes": "0",
     "total-records": "26404189"
    }
   }
  ]
 }
}
''')


def expected(case, size, seed):
    return _GOLDEN[f"{case}|{size}|{seed}"]
