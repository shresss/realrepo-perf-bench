"""Workload for the PyIceberg commit-path task: append Arrow batches to a SqlCatalog table with a long history.

run(case, size, seed) builds a deterministic local Iceberg table (SQLite catalog + local warehouse) in a fresh
temporary directory, then calls the public PyIceberg write API (Table.append / Table.delete / Transaction) and
returns JSON-able observables (snapshot summaries, parent linkage, added files, table properties).

`size` is the number of historical append snapshots already present on the table (10 data files each, compacted
into at most 10 manifests). The performance case appends one 240,000-row batch spanning 30 days x 8 regions, which
the writer splits into 240 data files (one per identity(region), identity(event_date) partition).

The workload runs single-threaded: PyIceberg's shared executor is replaced by an inline executor and Arrow's pools
are set to one thread. This is part of the declared environment, not of the code under test.
"""
import hashlib
import json
import os
import random
import tempfile
import uuid

REGIONS = ["us-east", "us-west", "eu-central", "eu-west", "ap-south", "ap-northeast", "sa-east", "af-south"]
DAY0 = 1_780_000_000_000 // 86_400_000 + 3  # first event day (days since epoch)

# case -> (days, regions, rows_per_partition, operations)
CASES = {
    "reload": (30, 8, 1000, ["append"]),
    "backfill": (60, 8, 250, ["append"]),
    "fast-small": (2, 3, 20, ["append"]),
    "merge-append-delete": (2, 3, 20, ["merge-on", "append", "delete-us-east"]),
    "merge-delete-none": (2, 3, 20, ["merge-on", "append", "delete-nowhere"]),
    "empty-table": (1, 2, 5, ["merge-on", "append", "delete-us-east"]),
    "tx-two-appends": (2, 3, 20, ["tx:append+append"]),
    "tx-props-then-append": (2, 3, 20, ["tx:partition-limit+append"]),
    "tx-schema-then-append": (2, 3, 20, ["tx:add-column+append"]),
}


def _single_thread():
    from concurrent.futures import Executor, Future

    class InlineExecutor(Executor):
        def submit(self, fn, /, *args, **kwargs):
            future = Future()
            try:
                future.set_result(fn(*args, **kwargs))
            except BaseException as exc:  # noqa: BLE001 - surfaced through the future like a pool would
                future.set_exception(exc)
            return future

    import pyarrow as pa
    import pyiceberg.utils.concurrent as concurrent

    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    group_by_init = pa.TableGroupBy.__init__

    def group_by_single_thread(self, table, keys, use_threads=True):
        group_by_init(self, table, keys, use_threads=False)

    pa.TableGroupBy.__init__ = group_by_single_thread
    # Table.filter / sort_by / group_by run Acero plans with use_threads=True; re-create those three pyarrow
    # helpers with use_threads=False (same pinned pyarrow source, only the threading flag differs).
    import inspect

    import pyarrow.acero as acero

    for name in ("_filter_table", "_sort_source", "_group_by"):
        source = inspect.getsource(getattr(acero, name)).replace("use_threads=True", "use_threads=False")
        exec(compile(source, acero.__file__, "exec"), acero.__dict__)  # noqa: S102 - pinned library source
    concurrent.ExecutorFactory._instance = InlineExecutor()
    concurrent.ExecutorFactory._instance_pid = os.getpid()


def _schema():
    from pyiceberg.schema import Schema
    from pyiceberg.types import DateType, DoubleType, LongType, NestedField, StringType, TimestampType

    return Schema(
        NestedField(1, "event_id", LongType(), required=False),
        NestedField(2, "event_ts", TimestampType(), required=False),
        NestedField(3, "region", StringType(), required=False),
        NestedField(4, "event_date", DateType(), required=False),
        NestedField(5, "c5", DoubleType(), required=False),
    )


def _spec():
    from pyiceberg.partitioning import PartitionField, PartitionSpec
    from pyiceberg.transforms import IdentityTransform

    return PartitionSpec(PartitionField(3, 1000, IdentityTransform(), "region"),
                         PartitionField(4, 1001, IdentityTransform(), "event_date"))


def _catalog(work):
    from pyiceberg.catalog.sql import SqlCatalog

    return SqlCatalog("fx", uri=f"sqlite:///{work}/catalog.db", warehouse=f"file://{work}/warehouse")


def _build_table(work, n_snapshots, seed, files_per_snapshot=10, n_manifests=10):
    """Create ops.events and, when n_snapshots > 0, give it a compacted history written with PyIceberg's writers."""
    from pyiceberg.conversions import to_bytes
    from pyiceberg.manifest import (DataFile, DataFileContent, FileFormat, ManifestEntry, ManifestEntryStatus,
                                    write_manifest, write_manifest_list)
    from pyiceberg.serializers import ToOutputFile
    from pyiceberg.table.metadata import SnapshotLogEntry
    from pyiceberg.table.refs import SnapshotRef, SnapshotRefType
    from pyiceberg.table.snapshots import Operation, Snapshot, Summary
    from pyiceberg.typedef import Record
    from pyiceberg.types import DateType, DoubleType, LongType, TimestampType

    cat = _catalog(work)
    cat.create_namespace("ops")
    schema, spec = _schema(), _spec()
    tbl = cat.create_table("ops.events", schema=schema, partition_spec=spec, properties={"format-version": "2"})
    if n_snapshots == 0:
        return cat
    rng = random.Random(seed)
    md, io = tbl.metadata, tbl.io
    loc = tbl.location().replace("file://", "")
    fields = list(schema.fields)
    used, snap_ids = set(), []
    for _ in range(n_snapshots):
        while True:
            s = rng.getrandbits(62)
            if s not in used:
                used.add(s)
                snap_ids.append(s)
                break
    t0 = 1_780_000_000_000
    ts = [t0 + i * 120_000 + rng.randrange(0, 60_000) for i in range(n_snapshots)]
    entries = []
    for i in range(n_snapshots):
        day = ts[i] // 86_400_000
        for j in range(files_per_snapshot):
            region = REGIONS[rng.randrange(len(REGIONS))]
            rc = rng.randrange(1_000, 200_000)
            lb, ub = {}, {}
            for f in fields:
                t = f.field_type
                if isinstance(t, LongType):
                    a, b = sorted((rng.getrandbits(40), rng.getrandbits(40)))
                elif isinstance(t, DoubleType):
                    a, b = sorted((rng.random() * 1e6, rng.random() * 1e6))
                elif isinstance(t, TimestampType):
                    a, b = ts[i] * 1000 - 3_600_000_000, ts[i] * 1000
                elif isinstance(t, DateType):
                    a = b = int(day)
                else:
                    a = b = region
                lb[f.field_id], ub[f.field_id] = to_bytes(t, a), to_bytes(t, b)
            df = DataFile.from_args(
                _table_format_version=2, content=DataFileContent.DATA,
                file_path=f"file://{loc}/data/region={region}/event_date={day}/{i:06d}-{j:03d}-{uuid.UUID(int=rng.getrandbits(128))}.parquet",
                file_format=FileFormat.PARQUET, partition=Record(region, int(day)), record_count=rc,
                file_size_in_bytes=rc * 37 + rng.randrange(0, 4096),
                column_sizes={f.field_id: rc * 4 for f in fields}, value_counts={f.field_id: rc for f in fields},
                null_value_counts={f.field_id: (0 if f.field_id in (3, 4) else rng.randrange(0, 3)) for f in fields},
                nan_value_counts={}, lower_bounds=lb, upper_bounds=ub, split_offsets=[4], sort_order_id=0, spec_id=0)
            entries.append((i, df))
    cur_id = rng.getrandbits(62)
    cur_seq = n_snapshots + 1
    per = max(1, (len(entries) + n_manifests - 1) // n_manifests)
    manifests = []
    for m in range(0, len(entries), per):
        out = io.new_output(f"{loc}/metadata/compacted-{m // per:05d}-m0.avro")
        with write_manifest(format_version=2, spec=spec, schema=schema, output_file=out, snapshot_id=cur_id,
                            avro_compression="deflate") as w:
            for i, df in entries[m:m + per]:
                w.existing(ManifestEntry.from_args(status=ManifestEntryStatus.EXISTING, snapshot_id=snap_ids[i],
                                                   sequence_number=i + 1, file_sequence_number=i + 1, data_file=df))
        manifests.append(w.to_manifest_file())
    ml = f"{loc}/metadata/snap-{cur_id}-1-current.avro"
    with write_manifest_list(format_version=2, output_file=io.new_output(ml), snapshot_id=cur_id,
                             parent_snapshot_id=snap_ids[-1], sequence_number=cur_seq, avro_compression="deflate") as w:
        w.add_manifests(manifests)
    # Historical snapshots were expired of their data by a compaction; they keep one shared empty manifest list.
    empty_ml = f"{loc}/metadata/snap-historical-empty.avro"
    with write_manifest_list(format_version=2, output_file=io.new_output(empty_ml), snapshot_id=snap_ids[0],
                             parent_snapshot_id=None, sequence_number=1, avro_compression="deflate") as w:
        w.add_manifests([])
    snaps, log, total_files, total_records = [], [], 0, 0
    for i in range(n_snapshots):
        added = [df for k, df in entries[i * files_per_snapshot:(i + 1) * files_per_snapshot]]
        total_files += len(added)
        total_records += sum(df.record_count for df in added)
        summary = Summary(Operation.APPEND, **{
            "added-data-files": str(len(added)), "added-records": str(sum(df.record_count for df in added)),
            "total-data-files": str(total_files), "total-records": str(total_records),
            "total-delete-files": "0", "total-position-deletes": "0", "total-equality-deletes": "0"})
        snaps.append(Snapshot(snapshot_id=snap_ids[i], parent_snapshot_id=snap_ids[i - 1] if i else None,
                              sequence_number=i + 1, timestamp_ms=ts[i], manifest_list=f"file://{empty_ml}",
                              summary=summary, schema_id=0))
        log.append(SnapshotLogEntry(snapshot_id=snap_ids[i], timestamp_ms=ts[i]))
    cur_ts = ts[-1] + 60_000
    snaps.append(Snapshot(snapshot_id=cur_id, parent_snapshot_id=snap_ids[-1], sequence_number=cur_seq,
                          timestamp_ms=cur_ts, manifest_list=f"file://{ml}", schema_id=0,
                          summary=Summary(Operation.REPLACE, **{
                              "total-data-files": str(total_files), "total-records": str(total_records),
                              "total-delete-files": "0", "total-position-deletes": "0",
                              "total-equality-deletes": "0"})))
    log.append(SnapshotLogEntry(snapshot_id=cur_id, timestamp_ms=cur_ts))
    new_md = md.model_copy(update={
        "snapshots": snaps, "snapshot_log": log, "current_snapshot_id": cur_id, "last_sequence_number": cur_seq,
        "last_updated_ms": cur_ts, "refs": {"main": SnapshotRef(snapshot_id=cur_id, snapshot_ref_type=SnapshotRefType.BRANCH)}})
    mpath = f"{loc}/metadata/00001-{uuid.UUID(int=rng.getrandbits(128))}.metadata.json"
    ToOutputFile.table_metadata(new_md, io.new_output(mpath))
    from sqlalchemy import text

    with cat.engine.begin() as conn:
        conn.execute(text("UPDATE iceberg_tables SET metadata_location=:m "
                          "WHERE table_namespace='ops' AND table_name='events'"), {"m": f"file://{mpath}"})
    return cat


def _batch(days, regions, rows, seed, extra_column=False):
    import pyarrow as pa

    rng = random.Random(seed)
    ids, tss, regs, dates, c5 = [], [], [], [], []
    for d in range(days):
        for r in range(regions):
            base_us = (DAY0 + d) * 86_400_000_000
            for _ in range(rows):
                ids.append(rng.getrandbits(40))
                tss.append(base_us + rng.randrange(86_400_000_000))
                regs.append(REGIONS[r])
                dates.append(DAY0 + d)
                c5.append(rng.random() * 1000)
    cols = {"event_id": pa.array(ids, pa.int64()), "event_ts": pa.array(tss, pa.timestamp("us")),
            "region": pa.array(regs, pa.string()), "event_date": pa.array(dates, pa.int32()).cast(pa.date32()),
            "c5": pa.array(c5, pa.float64())}
    if extra_column:
        cols["channel"] = pa.array([("web", "app", "api")[i % 3] for i in range(len(ids))], pa.string())
    return pa.table(cols)


def _snapshot_view(tbl, before_id):
    snap = tbl.current_snapshot()
    summary = dict(snap.summary.additional_properties)
    return {"operation": str(snap.summary.operation), "summary": dict(sorted(summary.items())),
            "parent_is_previous_current": snap.parent_snapshot_id == before_id}


def _added_files(tbl, snapshot):
    rows = []
    for manifest in snapshot.manifests(tbl.io):
        if manifest.added_snapshot_id != snapshot.snapshot_id:
            continue
        for entry in manifest.fetch_manifest_entry(tbl.io, discard_deleted=True):
            if entry.snapshot_id == snapshot.snapshot_id and int(entry.status) == 1:
                p = entry.data_file.partition
                rows.append([str(p[0]), int(p[1]), int(entry.data_file.record_count)])
    return sorted(rows)


def run(case, size, seed):
    from pyiceberg.expressions import EqualTo

    _single_thread()
    days, regions, rows, ops = CASES[case]
    work = tempfile.mkdtemp(prefix="iceberg-workload-")
    cat = _build_table(work, size, seed)
    tbl = cat.load_table("ops.events")
    batch = _batch(days, regions, rows, seed + 7)
    steps = []
    for op in ops:
        before = tbl.current_snapshot().snapshot_id if tbl.current_snapshot() else None
        if op == "merge-on":
            with tbl.transaction() as tx:
                tx.set_properties(**{"commit.manifest-merge.enabled": "true"})
            continue
        if op == "append":
            tbl.append(batch)
        elif op == "delete-us-east":
            tbl.delete(EqualTo("region", "us-east"))
        elif op == "delete-nowhere":
            tbl.delete(EqualTo("region", "nowhere"))
        elif op == "tx:append+append":
            half = batch.num_rows // 2
            with tbl.transaction() as tx:
                tx.append(batch.slice(0, half))
                tx.append(batch.slice(half))
            tbl = cat.load_table("ops.events")
            snap = tbl.current_snapshot()
            parent = tbl.snapshot_by_id(snap.parent_snapshot_id)
            steps.append({"operation": str(parent.summary.operation),
                          "summary": dict(sorted(parent.summary.additional_properties.items())),
                          "parent_is_previous_current": parent.parent_snapshot_id == before})
            steps.append({"operation": str(snap.summary.operation),
                          "summary": dict(sorted(snap.summary.additional_properties.items())),
                          "parent_is_previous_current": snap.parent_snapshot_id == parent.snapshot_id})
            continue
        elif op == "tx:partition-limit+append":
            with tbl.transaction() as tx:
                tx.set_properties(**{"write.summary.partition-limit": "100"})
                tx.append(batch)
        elif op == "tx:add-column+append":
            import pyarrow as pa
            from pyiceberg.types import StringType

            wide = _batch(days, regions, rows, seed + 7, extra_column=True)
            with tbl.transaction() as tx:
                with tx.update_schema() as update:
                    update.add_column("channel", StringType())
                tx.append(wide)
        tbl = cat.load_table("ops.events")
        steps.append(_snapshot_view(tbl, before))
    tbl = cat.load_table("ops.events")
    snap = tbl.current_snapshot()
    added = _added_files(tbl, snap) if snap is not None else []
    canon = json.dumps(added, separators=(",", ":"))
    return {
        "case": case, "size": size, "seed": seed,
        "steps": steps,
        "snapshots": len(tbl.metadata.snapshots),
        "schema_fields": [f.name for f in tbl.schema().fields],
        "properties": dict(sorted(tbl.properties.items())),
        "added_files_count": len(added),
        "added_files_sha256": hashlib.sha256(canon.encode()).hexdigest(),
        "added_files": added if len(added) <= 12 else None,
    }


if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="reload", choices=sorted(CASES))
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    started = time.process_time()
    result = run(args.case, args.size, args.seed)
    result["cpu_seconds_whole_run"] = round(time.process_time() - started, 3)
    print(json.dumps(result, indent=1, sort_keys=True))
