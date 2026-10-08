"""Contract tests for F01's verifier-owned SQL measurement boundary.

These tests intentionally exercise the real Unix-socket protocol.  They do not
mock SQLite, the service process, or the remote client: the property under test
is that evidence is produced outside the process whose code is being measured.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest


TESTS_DIR = Path(__file__).resolve().parent
TASK_DIR = TESTS_DIR.parent


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


SERVICE_MODULE = _load_module(
    "f01_trusted_sqlite_service_for_tests",
    TESTS_DIR / "trusted_sqlite_service.py",
)
VISIBLE_SERVICE_PATH = (
    TASK_DIR / "environment" / "app" / "workloads" / "visible_sqlite_service.py"
)
if not VISIBLE_SERVICE_PATH.exists():
    VISIBLE_SERVICE_PATH = TESTS_DIR / "pristine" / "visible_sqlite_service.py"
VISIBLE_SERVICE_MODULE = _load_module(
    "f01_visible_sqlite_service_contract_for_tests",
    VISIBLE_SERVICE_PATH,
)
REMOTE_CLIENT_PATH = TASK_DIR / "environment" / "app" / "ledgerly" / "db" / "remote.py"
if not REMOTE_CLIENT_PATH.exists():
    # The separate verifier image is built with tests/ as its Docker context.
    REMOTE_CLIENT_PATH = TESTS_DIR / "pristine_src" / "ledgerly" / "db" / "remote.py"
REMOTE_MODULE = _load_module(
    "f01_remote_client_for_tests",
    REMOTE_CLIENT_PATH,
)

MeteredSQLiteService = SERVICE_MODULE.MeteredSQLiteService
RemoteDatabaseError = REMOTE_MODULE.RemoteDatabaseError
connect_remote = REMOTE_MODULE.connect_remote


def test_visible_and_hidden_service_protocol_limits_match():
    assert VISIBLE_SERVICE_MODULE.MAX_REQUEST_BYTES == SERVICE_MODULE.MAX_REQUEST_BYTES
    assert VISIBLE_SERVICE_MODULE.MAX_RESPONSE_BYTES == SERVICE_MODULE.MAX_RESPONSE_BYTES
    assert VISIBLE_SERVICE_MODULE.MAX_ROWS_PER_REQUEST == SERVICE_MODULE.MAX_ROWS_PER_REQUEST
    assert VISIBLE_SERVICE_MODULE.MAX_CELLS_PER_REQUEST == SERVICE_MODULE.MAX_CELLS_PER_REQUEST
    assert VISIBLE_SERVICE_MODULE.MAX_PARAMETERS == SERVICE_MODULE.MAX_PARAMETERS
    assert VISIBLE_SERVICE_MODULE.MAX_TOTAL_REQUESTS == SERVICE_MODULE.MAX_TOTAL_REQUESTS
    assert VISIBLE_SERVICE_MODULE.MAX_CONCURRENT_QUERIES == SERVICE_MODULE.MAX_CONCURRENT_QUERIES
    assert VISIBLE_SERVICE_MODULE.MAX_ACTIVE_CONNECTIONS == SERVICE_MODULE.MAX_ACTIVE_CONNECTIONS
    assert (
        VISIBLE_SERVICE_MODULE.MAX_TOTAL_HANDLER_CONNECTIONS
        == SERVICE_MODULE.MAX_TOTAL_HANDLER_CONNECTIONS
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wire_bytes(payload: dict) -> int:
    """Encode independently with the documented compact JSON-line protocol."""

    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _create_database(path: Path, *, scan_rows: int = 0) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                amount_cents INTEGER NOT NULL
            );
            INSERT INTO items (id, name, amount_cents) VALUES
                (1, 'alpha', 100),
                (2, 'βeta', 250),
                (3, 'gamma', 400);
            """
        )
        if scan_rows:
            connection.execute(
                "CREATE TABLE scan_values (id INTEGER PRIMARY KEY, payload INTEGER NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO scan_values (id, payload) VALUES (?, ?)",
                ((index, index % 997) for index in range(1, scan_rows + 1)),
            )
        connection.commit()
    finally:
        connection.close()


@contextmanager
def _running_service(
    *,
    scan_rows: int = 0,
    max_active_connections: int = SERVICE_MODULE.MAX_ACTIVE_CONNECTIONS,
    max_total_handler_connections: int = (
        SERVICE_MODULE.MAX_TOTAL_HANDLER_CONNECTIONS
    ),
):
    """Run the actual meter in a short socket path and always reap it."""

    directory = Path(tempfile.mkdtemp(prefix="f01-meter-test-", dir="/tmp"))
    database_path = directory / "fixture.sqlite3"
    socket_path = directory / "db.sock"
    _create_database(database_path, scan_rows=scan_rows)
    database_sha256 = _sha256(database_path)
    attempt_id = f"test-{uuid.uuid4().hex}"
    service = MeteredSQLiteService(
        str(database_path),
        str(socket_path),
        attempt_id,
        database_sha256,
        drop_privileges=False,
        uid=os.getuid(),
        gid=os.getgid(),
        max_active_connections=max_active_connections,
        max_total_handler_connections=max_total_handler_connections,
    )
    ready = service.start()
    try:
        yield {
            "service": service,
            "url": f"metered+unix://{socket_path}",
            "socket_path": socket_path,
            "database_path": database_path,
            "database_sha256": database_sha256,
            "attempt_id": attempt_id,
            "ready": ready,
        }
    finally:
        service.abort()
        shutil.rmtree(directory, ignore_errors=True)


def _read_connection_denial(socket_path: Path) -> dict:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(2.0)
    try:
        client.connect(str(socket_path))
        chunks = bytearray()
        while b"\n" not in chunks:
            part = client.recv(4096)
            if not part:
                break
            chunks.extend(part)
        assert chunks.endswith(b"\n")
        response = json.loads(bytes(chunks))
        assert response["ok"] is False
        assert response["error_type"] == "PolicyDenied"
        return response
    finally:
        client.close()


def test_select_has_exact_server_owned_metrics_and_digest_binding():
    sql = "SELECT id, name, amount_cents FROM items WHERE id >= ? ORDER BY id"
    params = [2]
    expected_rows = [[2, "βeta", 250], [3, "gamma", 400]]

    with _running_service() as run:
        assert run["ready"]["attempt_id"] == run["attempt_id"]
        assert run["ready"]["database_sha256"] == run["database_sha256"]

        with connect_remote(run["url"]) as connection:
            cursor = connection.execute(sql, params)
            rows = cursor.fetchall()
            assert cursor.description[0][0] == "id"
            assert rows[0]["name"] == "βeta"
            assert [list(row) for row in rows] == expected_rows

        metrics = run["service"].stop()

        expected_request_bytes = _wire_bytes(
            {"request_id": 1, "sql": sql, "params": params}
        )
        expected_response_bytes = _wire_bytes(
            {
                "ok": True,
                "request_id": 1,
                "columns": ["id", "name", "amount_cents"],
                "rows": expected_rows,
            }
        )
        vm_callbacks = metrics["sqlite_vm_progress_callbacks_total"]
        vm_callback_quanta = (
            vm_callbacks * SERVICE_MODULE.SQLITE_VM_PROGRESS_STEPS
        )
        vm_query_lower_bound = (
            max(0, vm_callbacks - 1) * SERVICE_MODULE.SQLITE_VM_PROGRESS_STEPS
        )
        vm_query_upper_bound = (
            (vm_callbacks + 1) * SERVICE_MODULE.SQLITE_VM_PROGRESS_STEPS
        )
        assert metrics == {
            "schema_version": 2,
            "attempt_id": run["attempt_id"],
            "database_sha256": run["database_sha256"],
            "max_active_connections": SERVICE_MODULE.MAX_ACTIVE_CONNECTIONS,
            "max_total_handler_connections": (
                SERVICE_MODULE.MAX_TOTAL_HANDLER_CONNECTIONS
            ),
            "max_total_requests": SERVICE_MODULE.MAX_TOTAL_REQUESTS,
            "max_cells_per_request": SERVICE_MODULE.MAX_CELLS_PER_REQUEST,
            "max_concurrent_queries": SERVICE_MODULE.MAX_CONCURRENT_QUERIES,
            "connections_seen": 1,
            "connections_accepted": 1,
            "connections_rejected": 0,
            "connections_rejected_active_limit": 0,
            "connections_rejected_total_limit": 0,
            "connections_rejected_handler_start": 0,
            "connection_rejection_response_bytes": 0,
            "peak_concurrent_connections": 1,
            "handler_threads_started": 1,
            "handler_start_failures": 0,
            "handler_runtime_failures": 0,
            "shutdown_integrity_failures": 0,
            "peak_retained_handler_threads": 1,
            "requests_total": 1,
            "requests_rejected_total_limit": 0,
            "request_limit_rejection_response_bytes": 0,
            "queries_succeeded": 1,
            "queries_failed": 0,
            "policy_denials": 0,
            "integrity_failures": 0,
            "rows_delivered": 2,
            "request_bytes": expected_request_bytes,
            "response_bytes": expected_response_bytes,
            "error_types": {},
            "sqlite_vm_progress_granularity": (
                SERVICE_MODULE.SQLITE_VM_PROGRESS_STEPS
            ),
            "sqlite_vm_queries_measured": 1,
            "sqlite_vm_queries_succeeded": 1,
            "sqlite_vm_queries_failed": 0,
            "sqlite_vm_queries_with_progress": int(vm_callbacks > 0),
            "sqlite_vm_progress_callbacks_total": vm_callbacks,
            "sqlite_vm_steps_lower_bound_total": vm_callback_quanta,
            "sqlite_vm_per_query_lower_bounds_succeeded_total": (
                vm_query_lower_bound
            ),
            "sqlite_vm_per_query_lower_bounds_failed_total": 0,
            "sqlite_vm_per_query_lower_bound_min": vm_query_lower_bound,
            "sqlite_vm_per_query_lower_bound_max": vm_query_lower_bound,
            "active_handlers_at_stop": 0,
            "retained_handler_threads_at_stop": 0,
            "database_sha256_after": run["database_sha256"],
            "vm_progress_callbacks": vm_callbacks,
            "vm_steps": vm_callback_quanta,
            "sqlite_vm_top_queries": [
                {
                    "sequence": 1,
                    "connection_id": 1,
                    "request_id": 1,
                    "outcome": "succeeded",
                    "progress_callbacks": vm_callbacks,
                    "callback_quanta": vm_callback_quanta,
                    "steps_lower_bound": vm_query_lower_bound,
                    "steps_upper_bound_exclusive": vm_query_upper_bound,
                }
            ],
        }
        assert _sha256(run["database_path"]) == run["database_sha256"]


def test_writes_attach_and_pragma_are_rejected_and_metered():
    forbidden_sql = [
        "INSERT INTO items (name, amount_cents) VALUES ('forged', 999)",
        "ATTACH DATABASE ':memory:' AS extra",
        "PRAGMA table_info(items)",
    ]

    with _running_service() as run:
        with connect_remote(run["url"]) as connection:
            for sql in forbidden_sql:
                with pytest.raises(RemoteDatabaseError, match="PolicyDenied"):
                    connection.execute(sql)

        metrics = run["service"].stop()
        assert metrics["requests_total"] == 3
        assert metrics["queries_succeeded"] == 0
        assert metrics["queries_failed"] == 3
        assert metrics["policy_denials"] == 3
        assert metrics["integrity_failures"] == 0
        assert metrics["rows_delivered"] == 0
        assert metrics["error_types"] == {"PolicyDenied": 3}
        assert metrics["sqlite_vm_queries_measured"] == 3
        assert metrics["sqlite_vm_queries_failed"] == 3
        assert metrics["sqlite_vm_per_query_lower_bounds_succeeded_total"] == 0
        assert metrics["database_sha256_after"] == run["database_sha256"]

        local = sqlite3.connect(run["database_path"])
        try:
            assert local.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 3
        finally:
            local.close()


def test_query_attributed_resource_limit_is_policy_not_integrity(monkeypatch):
    assert SERVICE_MODULE._is_request_resource_error("out of memory")
    assert SERVICE_MODULE._is_request_resource_error("database or disk is full")
    assert SERVICE_MODULE._is_request_resource_error("string or blob too big")
    assert not SERVICE_MODULE._is_request_resource_error("disk I/O error")
    assert not SERVICE_MODULE._is_request_resource_error(
        "database disk image is malformed"
    )

    # Large enough for the service to encode a compact denial, but too small
    # for the deliberately broad result below.  The forked worker inherits the
    # patched cap, exercising the real request/error/metrics path.
    monkeypatch.setattr(SERVICE_MODULE, "MAX_RESPONSE_BYTES", 1024)
    with _running_service(scan_rows=500) as run:
        with connect_remote(run["url"]) as connection:
            with pytest.raises(RemoteDatabaseError, match="PolicyDenied"):
                connection.execute(
                    "SELECT id, payload FROM scan_values ORDER BY id"
                )

        metrics = run["service"].stop()
        assert metrics["requests_total"] == 1
        assert metrics["queries_succeeded"] == 0
        assert metrics["queries_failed"] == 1
        assert metrics["policy_denials"] == 1
        assert metrics["integrity_failures"] == 0
        assert metrics["error_types"] == {"PolicyDenied": 1}
        assert metrics["sqlite_vm_queries_measured"] == 1
        assert metrics["sqlite_vm_queries_failed"] == 1
        assert metrics["sqlite_vm_per_query_lower_bounds_failed_total"] > 0


def test_cell_limit_stops_materialization_before_response_encoding(monkeypatch):
    """A broad result is rejected while it is still bounded in memory."""

    monkeypatch.setattr(SERVICE_MODULE, "MAX_CELLS_PER_REQUEST", 3)
    with _running_service() as run:
        with connect_remote(run["url"]) as connection:
            with pytest.raises(RemoteDatabaseError, match="PolicyDenied"):
                connection.execute(
                    "SELECT id, name FROM items ORDER BY id"
                ).fetchall()

        metrics = run["service"].stop()
        assert metrics["max_cells_per_request"] == 3
        assert metrics["queries_succeeded"] == 0
        assert metrics["queries_failed"] == 1
        assert metrics["policy_denials"] == 1
        assert metrics["integrity_failures"] == 0
        assert metrics["rows_delivered"] == 0


def test_nonquiescent_handler_shutdown_is_integrity_loss(monkeypatch):
    """Final evidence is not valid while admitted handler work remains alive."""

    def stuck_handler(*_args, **_kwargs):
        time.sleep(5.0)

    monkeypatch.setattr(SERVICE_MODULE, "_handle_client", stuck_handler)
    with _running_service() as run:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(run["socket_path"]))
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            time.sleep(0.01)
            # The accepted connection is enough; stop promptly so the injected
            # handler is still alive after the service's bounded join.
            break
        metrics = run["service"].stop()
        client.close()
        assert metrics["active_handlers_at_stop"] == 1
        assert metrics["retained_handler_threads_at_stop"] == 1
        assert metrics["shutdown_integrity_failures"] == 1
        assert metrics["integrity_failures"] == 1
        assert metrics["policy_denials"] == 0
        assert metrics["error_types"] == {"NonQuiescentShutdown": 1}


def test_handler_start_failure_is_integrity_loss_not_candidate_policy():
    """A host that cannot honor admitted capacity is not a model failure."""

    metrics = SERVICE_MODULE._SharedMetrics(
        "handler-start-test",
        "a" * 64,
        max_active_connections=2,
        max_total_handler_connections=3,
    )
    metrics.connection_rejected(
        "handler_start",
        0,
        policy_denial=False,
        integrity_failure=True,
    )
    snapshot = metrics.snapshot(
        active_handlers=0,
        retained_handler_threads=0,
        database_sha256_after="a" * 64,
    )
    assert snapshot["connections_rejected"] == 1
    assert snapshot["connections_rejected_handler_start"] == 1
    assert snapshot["policy_denials"] == 0
    assert snapshot["integrity_failures"] == 1
    assert snapshot["error_types"] == {"HandlerStartFailure": 1}


def test_total_request_budget_is_typed_policy_denial(monkeypatch):
    monkeypatch.setattr(SERVICE_MODULE, "MAX_TOTAL_REQUESTS", 2)
    with _running_service() as run:
        with connect_remote(run["url"]) as connection:
            assert connection.execute("SELECT 1").fetchone()[0] == 1
            assert connection.execute("SELECT 2").fetchone()[0] == 2
            with pytest.raises(RemoteDatabaseError, match="PolicyDenied"):
                connection.execute("SELECT 3")

        metrics = run["service"].stop()
        assert metrics["max_total_requests"] == 2
        assert metrics["requests_total"] == 2
        assert metrics["requests_rejected_total_limit"] == 1
        assert metrics["policy_denials"] == 1
        assert metrics["integrity_failures"] == 0
        assert metrics["error_types"] == {"PolicyDenied": 1}
        assert metrics["request_limit_rejection_response_bytes"] > 0


def test_unexpected_handler_failure_is_reported_as_integrity_loss(monkeypatch):
    def fail_handler(*_args, **_kwargs):
        raise MemoryError("injected handler failure")

    monkeypatch.setattr(SERVICE_MODULE, "_handle_client", fail_handler)
    with _running_service() as run:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(run["socket_path"]))
        client.close()
        deadline = time.monotonic() + 2.0
        metrics = None
        while metrics is None and time.monotonic() < deadline:
            try:
                metrics = run["service"].stop()
            except RuntimeError as exc:
                # stop() is single-shot; this branch is only a clearer failure if
                # the injected handler prevents final evidence unexpectedly.
                pytest.fail(str(exc))
        assert metrics is not None
        assert metrics["handler_runtime_failures"] == 1
        assert metrics["integrity_failures"] == 1
        assert metrics["policy_denials"] == 0
        assert metrics["error_types"] == {"HandlerRuntime:MemoryError": 1}


def test_metrics_aggregate_across_multiple_persistent_connections():
    with _running_service() as run:
        first = connect_remote(run["url"])
        second = connect_remote(run["url"])
        try:
            assert first.execute(
                "SELECT id FROM items WHERE id = ?", (1,)
            ).fetchone()[0] == 1
            assert [row[0] for row in second.execute(
                "SELECT id FROM items WHERE id >= ? ORDER BY id", (2,)
            )] == [2, 3]
        finally:
            first.close()
            second.close()

        metrics = run["service"].stop()
        assert metrics["connections_accepted"] == 2
        assert metrics["peak_concurrent_connections"] == 2
        assert metrics["requests_total"] == 2
        assert metrics["queries_succeeded"] == 2
        assert metrics["queries_failed"] == 0
        assert metrics["integrity_failures"] == 0
        assert metrics["rows_delivered"] == 3


def test_client_local_metric_forgery_cannot_change_service_report():
    with _running_service() as run:
        # Simulate the exact class of attack that invalidates in-process meters:
        # submission code invents or mutates counters in its own interpreter.
        REMOTE_MODULE.statements_executed = -1_000_000
        REMOTE_MODULE.rows_delivered = -1_000_000
        REMOTE_MODULE.response_bytes = -1_000_000

        with connect_remote(run["url"]) as connection:
            connection.statements_executed = 0
            connection.rows_delivered = 0
            connection.response_bytes = 0
            assert connection.execute("SELECT COUNT(*) AS count FROM items").fetchone()[
                "count"
            ] == 3
            connection.statements_executed = 10**18
            connection.rows_delivered = 10**18
            connection.response_bytes = 10**18

        metrics = run["service"].stop()
        assert metrics["requests_total"] == 1
        assert metrics["queries_succeeded"] == 1
        assert metrics["rows_delivered"] == 1
        assert metrics["request_bytes"] > 0
        assert metrics["response_bytes"] > 0
        assert metrics["database_sha256_after"] == run["database_sha256"]


def test_idle_connection_flood_is_bounded_and_service_survives():
    flood_count = 64
    with _running_service(
        max_active_connections=2,
        max_total_handler_connections=3,
    ) as run:
        first = connect_remote(run["url"])
        second = connect_remote(run["url"])
        try:
            assert first.execute("SELECT id FROM items WHERE id = 1").fetchone()[
                0
            ] == 1
            assert second.execute("SELECT id FROM items WHERE id = 2").fetchone()[
                0
            ] == 2

            active_denials = [
                _read_connection_denial(run["socket_path"])
                for _ in range(flood_count)
            ]
            assert all(
                "active database connection limit" in denial["error"]
                for denial in active_denials
            )
        finally:
            first.close()
            second.close()

        # Closing the idle/persistent holders must release capacity.  A normal
        # request then proves the meter survived the flood.  A short retry loop
        # accommodates the handler observing EOF asynchronously.
        deadline = time.monotonic() + 3.0
        survivor = None
        while survivor is None and time.monotonic() < deadline:
            candidate = None
            try:
                candidate = connect_remote(run["url"])
                assert candidate.execute(
                    "SELECT COUNT(*) AS count FROM items"
                ).fetchone()["count"] == 3
                survivor = candidate
            except (OSError, RemoteDatabaseError):
                if candidate is not None:
                    candidate.close()
                time.sleep(0.01)
        assert survivor is not None
        survivor.close()

        total_denial = _read_connection_denial(run["socket_path"])
        assert "total database connection limit" in total_denial["error"]

        metrics = run["service"].stop()
        assert metrics["max_active_connections"] == 2
        assert metrics["max_total_handler_connections"] == 3
        assert metrics["connections_accepted"] == 3
        assert metrics["handler_threads_started"] == 3
        assert metrics["handler_start_failures"] == 0
        assert metrics["peak_concurrent_connections"] == 2
        assert metrics["peak_retained_handler_threads"] <= 2
        assert metrics["connections_rejected_active_limit"] >= flood_count
        assert metrics["connections_rejected_total_limit"] == 1
        assert metrics["connections_rejected_handler_start"] == 0
        assert metrics["connections_rejected"] == (
            metrics["connections_rejected_active_limit"] + 1
        )
        assert metrics["connections_seen"] == (
            metrics["connections_accepted"] + metrics["connections_rejected"]
        )
        assert metrics["policy_denials"] == metrics["connections_rejected"]
        assert metrics["error_types"] == {
            "PolicyDenied": metrics["connections_rejected"]
        }
        assert metrics["integrity_failures"] == 0
        assert metrics["requests_total"] == 3
        assert metrics["active_handlers_at_stop"] == 0
        assert metrics["retained_handler_threads_at_stop"] == 0


def test_vm_progress_evidence_increases_for_larger_scan():
    with _running_service(scan_rows=100_000) as run:
        with connect_remote(run["url"]) as connection:
            assert connection.execute(
                "SELECT payload FROM scan_values WHERE id = ?", (1,)
            ).fetchone()[0] == 1
            expected_sum = connection.execute(
                "SELECT SUM(payload) FROM scan_values WHERE payload >= ?", (0,)
            ).fetchone()[0]
            assert expected_sum > 0

        metrics = run["service"].stop()
        granularity = SERVICE_MODULE.SQLITE_VM_PROGRESS_STEPS
        assert metrics["sqlite_vm_progress_granularity"] == granularity
        assert metrics["sqlite_vm_queries_measured"] == 2
        assert metrics["sqlite_vm_queries_succeeded"] == 2
        assert metrics["sqlite_vm_queries_failed"] == 0
        assert metrics["sqlite_vm_queries_with_progress"] >= 1
        assert metrics["sqlite_vm_progress_callbacks_total"] > 0
        assert metrics["sqlite_vm_steps_lower_bound_total"] == (
            metrics["sqlite_vm_progress_callbacks_total"] * granularity
        )
        assert metrics[
            "sqlite_vm_per_query_lower_bounds_succeeded_total"
        ] <= metrics[
            "sqlite_vm_steps_lower_bound_total"
        ]
        assert metrics["sqlite_vm_per_query_lower_bounds_failed_total"] == 0

        samples = {
            sample["request_id"]: sample
            for sample in metrics["sqlite_vm_top_queries"]
        }
        assert samples[2]["steps_lower_bound"] > samples[1]["steps_lower_bound"]
        assert samples[2]["progress_callbacks"] > samples[1][
            "progress_callbacks"
        ]
        assert metrics["sqlite_vm_per_query_lower_bound_min"] == samples[1][
            "steps_lower_bound"
        ]
        assert metrics["sqlite_vm_per_query_lower_bound_max"] == samples[2][
            "steps_lower_bound"
        ]


def test_vm_total_accumulates_across_short_indexed_requests():
    request_count = 250
    with _running_service() as run:
        with connect_remote(run["url"]) as connection:
            for index in range(request_count):
                row = connection.execute(
                    "SELECT name FROM items WHERE id = ?", ((index % 3) + 1,)
                ).fetchone()
                assert row[0]

        metrics = run["service"].stop()
        granularity = SERVICE_MODULE.SQLITE_VM_PROGRESS_STEPS
        assert metrics["requests_total"] == request_count
        assert metrics["sqlite_vm_queries_measured"] == request_count
        assert metrics["sqlite_vm_progress_callbacks_total"] > 0
        assert metrics["sqlite_vm_steps_lower_bound_total"] == (
            metrics["sqlite_vm_progress_callbacks_total"] * granularity
        )
        assert metrics["sqlite_vm_steps_lower_bound_total"] > request_count
        assert len(metrics["sqlite_vm_top_queries"]) == (
            SERVICE_MODULE.MAX_VM_TOP_QUERY_SAMPLES
        )
