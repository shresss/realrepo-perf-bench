"""Verifier-owned SQLite service and server-side resource meter.

Submitted code never imports this module.  The root verifier forks a dedicated
service process, gives it a private read-only hidden database, then drops it to a
UID different from the task process.  SQL request, row-transfer, and byte metrics
return over a parent-owned multiprocessing pipe that is not inherited by the
task child.
"""
from __future__ import annotations

import base64
import ctypes
import heapq
import hashlib
import json
import math
import multiprocessing
import os
import resource
import select
import socket
import sqlite3
import threading
import time
from collections import Counter
from typing import Any

MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_ROWS_PER_REQUEST = 500_000
MAX_CELLS_PER_REQUEST = 3_000_000
MAX_PARAMETERS = 50_000
MAX_TOTAL_REQUESTS = 1_000_000
MAX_CONCURRENT_QUERIES = 1
QUERY_TIMEOUT_SECONDS = 15.0
# A 100-operation interval keeps aggregate work from repeated short indexed
# N+1 reads visible while avoiding material observer cost on row-producing
# scans.  The callback product is an aggregate lower bound regardless of where
# SQLite resets its countdown; individual queries use conservative phase ranges.
SQLITE_VM_PROGRESS_STEPS = 100
SERVICE_ADDRESS_SPACE_BYTES = 1536 * 1024 * 1024
SERVICE_CPU_SECONDS = 650
SERVICE_OPEN_FILES = 256
SERVICE_PROCESSES = 64
MAX_ACTIVE_CONNECTIONS = 4
MAX_TOTAL_HANDLER_CONNECTIONS = 64
MAX_VM_TOP_QUERY_SAMPLES = 16

_ALLOWED_AUTHORIZER_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
}
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    _ALLOWED_AUTHORIZER_ACTIONS.add(sqlite3.SQLITE_RECURSIVE)

_DENIED_FUNCTIONS = {"load_extension", "readfile", "writefile"}
_INTEGRITY_ERROR_FRAGMENTS = {
    "disk i/o error",
    "database disk image is malformed",
    "file is not a database",
}
_REQUEST_RESOURCE_ERROR_FRAGMENTS = {
    "interrupted",
    "out of memory",
    "database or disk is full",
    "string or blob too big",
    "too many sql variables",
    "too many columns",
    "too many terms in compound select",
    "exceeds the service byte limit",
    "exceeds the service row limit",
}


def _is_request_resource_error(message: str) -> bool:
    lowered = message.lower()
    return any(fragment in lowered for fragment in _REQUEST_RESOURCE_ERROR_FRAGMENTS)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _drop_service_identity(uid: int, gid: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_NO_NEW_PRIVS) failed")
    os.umask(0o077)
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_AS,
        (SERVICE_ADDRESS_SPACE_BYTES, SERVICE_ADDRESS_SPACE_BYTES),
    )
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (SERVICE_CPU_SECONDS, SERVICE_CPU_SECONDS),
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_NOFILE,
        (SERVICE_OPEN_FILES, SERVICE_OPEN_FILES),
    )
    resource.setrlimit(
        resource.RLIMIT_NPROC,
        (SERVICE_PROCESSES, SERVICE_PROCESSES),
    )


def _safe_json_value(value: Any):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite SQLite value")
        return value
    if isinstance(value, bytes):
        return {"__bytes_b64__": base64.b64encode(value).decode("ascii")}
    raise ValueError(f"unsupported SQLite value type: {type(value).__name__}")


class _SharedMetrics:
    def __init__(
        self,
        attempt_id: str,
        database_sha256: str,
        *,
        max_active_connections: int,
        max_total_handler_connections: int,
    ):
        self.lock = threading.Lock()
        self.data = {
            "schema_version": 2,
            "attempt_id": attempt_id,
            "database_sha256": database_sha256,
            "max_active_connections": max_active_connections,
            "max_total_handler_connections": max_total_handler_connections,
            "max_total_requests": MAX_TOTAL_REQUESTS,
            "max_cells_per_request": MAX_CELLS_PER_REQUEST,
            "max_concurrent_queries": MAX_CONCURRENT_QUERIES,
            "connections_seen": 0,
            "connections_accepted": 0,
            "connections_rejected": 0,
            "connections_rejected_active_limit": 0,
            "connections_rejected_total_limit": 0,
            "connections_rejected_handler_start": 0,
            "connection_rejection_response_bytes": 0,
            "peak_concurrent_connections": 0,
            "handler_threads_started": 0,
            "handler_start_failures": 0,
            "handler_runtime_failures": 0,
            "shutdown_integrity_failures": 0,
            "peak_retained_handler_threads": 0,
            "requests_total": 0,
            "requests_rejected_total_limit": 0,
            "request_limit_rejection_response_bytes": 0,
            "queries_succeeded": 0,
            "queries_failed": 0,
            "policy_denials": 0,
            "integrity_failures": 0,
            "rows_delivered": 0,
            "request_bytes": 0,
            "response_bytes": 0,
            "error_types": Counter(),
            "sqlite_vm_progress_granularity": SQLITE_VM_PROGRESS_STEPS,
            "sqlite_vm_queries_measured": 0,
            "sqlite_vm_queries_succeeded": 0,
            "sqlite_vm_queries_failed": 0,
            "sqlite_vm_queries_with_progress": 0,
            "sqlite_vm_progress_callbacks_total": 0,
            "sqlite_vm_steps_lower_bound_total": 0,
            "sqlite_vm_per_query_lower_bounds_succeeded_total": 0,
            "sqlite_vm_per_query_lower_bounds_failed_total": 0,
            "sqlite_vm_per_query_lower_bound_min": None,
            "sqlite_vm_per_query_lower_bound_max": 0,
        }
        self._active_connections = 0
        self._connection_sequence = 0
        self._vm_query_sequence = 0
        self._vm_top_queries: list[
            tuple[int, int, int, int | None, str, int, int, int]
        ] = []

    def connection_seen(self) -> None:
        with self.lock:
            self.data["connections_seen"] += 1

    def connection_opened(self) -> int:
        with self.lock:
            self._connection_sequence += 1
            connection_id = self._connection_sequence
            self.data["connections_accepted"] += 1
            self._active_connections += 1
            self.data["peak_concurrent_connections"] = max(
                self.data["peak_concurrent_connections"],
                self._active_connections,
            )
            return connection_id

    def connection_closed(self) -> None:
        with self.lock:
            self._active_connections = max(0, self._active_connections - 1)

    def connection_rejected(
        self,
        reason: str,
        response_bytes: int,
        *,
        policy_denial: bool,
        integrity_failure: bool = False,
    ) -> None:
        key_by_reason = {
            "active_limit": "connections_rejected_active_limit",
            "total_limit": "connections_rejected_total_limit",
            "handler_start": "connections_rejected_handler_start",
        }
        with self.lock:
            self.data["connections_rejected"] += 1
            self.data[key_by_reason[reason]] += 1
            self.data["connection_rejection_response_bytes"] += response_bytes
            self.data["response_bytes"] += response_bytes
            if policy_denial:
                self.data["policy_denials"] += 1
                self.data["error_types"]["PolicyDenied"] += 1
            if integrity_failure:
                self.data["integrity_failures"] += 1
                self.data["error_types"]["HandlerStartFailure"] += 1

    def handler_thread_reserved(self, retained_threads: int) -> None:
        with self.lock:
            self.data["peak_retained_handler_threads"] = max(
                self.data["peak_retained_handler_threads"], retained_threads
            )

    def handler_thread_started(self) -> None:
        with self.lock:
            self.data["handler_threads_started"] += 1

    def handler_thread_start_failed(self) -> None:
        with self.lock:
            self.data["handler_start_failures"] += 1

    def handler_runtime_failed(self, error_type: str) -> None:
        with self.lock:
            self.data["handler_runtime_failures"] += 1
            self.data["integrity_failures"] += 1
            self.data["error_types"][f"HandlerRuntime:{error_type}"] += 1

    def shutdown_not_quiescent(
        self, active_handlers: int, retained_handler_threads: int
    ) -> None:
        """Mark final evidence incomplete when handler work outlives shutdown."""

        with self.lock:
            self.data["shutdown_integrity_failures"] += 1
            self.data["integrity_failures"] += 1
            self.data["error_types"]["NonQuiescentShutdown"] += 1

    def request_started(self, request_bytes: int) -> bool:
        with self.lock:
            if self.data["requests_total"] >= self.data["max_total_requests"]:
                self.data["requests_rejected_total_limit"] += 1
                self.data["policy_denials"] += 1
                self.data["error_types"]["PolicyDenied"] += 1
                return False
            self.data["requests_total"] += 1
            self.data["request_bytes"] += request_bytes
            return True

    def request_limit_rejection_sent(self, response_bytes: int) -> None:
        with self.lock:
            self.data["request_limit_rejection_response_bytes"] += response_bytes
            self.data["response_bytes"] += response_bytes

    def request_succeeded(self, rows: int, response_bytes: int) -> None:
        with self.lock:
            self.data["queries_succeeded"] += 1
            self.data["rows_delivered"] += rows
            self.data["response_bytes"] += response_bytes

    def request_failed(
        self,
        error_type: str,
        response_bytes: int,
        *,
        policy_denial: bool,
        integrity_failure: bool = False,
    ) -> None:
        with self.lock:
            self.data["queries_failed"] += 1
            if policy_denial:
                self.data["policy_denials"] += 1
            if integrity_failure:
                self.data["integrity_failures"] += 1
            self.data["response_bytes"] += response_bytes
            self.data["error_types"][error_type] += 1

    def sqlite_query_finished(
        self,
        connection_id: int,
        request_id: int | None,
        progress_callbacks: int,
        *,
        succeeded: bool,
    ) -> None:
        """Record quantized VM work once for one attempted SQLite statement.

        SQLite calls the progress handler every ``SQLITE_VM_PROGRESS_STEPS`` VM
        operations.  Its countdown spans statements on one connection.  The
        summed callback product is a strong connection-level lower bound; each
        sampled statement carries a conservative range for its unknown phase.
        """

        callbacks = max(0, int(progress_callbacks))
        callback_quanta = callbacks * SQLITE_VM_PROGRESS_STEPS
        lower_bound = max(0, callbacks - 1) * SQLITE_VM_PROGRESS_STEPS
        upper_bound_exclusive = (callbacks + 1) * SQLITE_VM_PROGRESS_STEPS
        outcome = "succeeded" if succeeded else "failed"
        with self.lock:
            self._vm_query_sequence += 1
            sequence = self._vm_query_sequence
            self.data["sqlite_vm_queries_measured"] += 1
            self.data[f"sqlite_vm_queries_{outcome}"] += 1
            self.data["sqlite_vm_progress_callbacks_total"] += callbacks
            self.data["sqlite_vm_steps_lower_bound_total"] += callback_quanta
            self.data[
                f"sqlite_vm_per_query_lower_bounds_{outcome}_total"
            ] += lower_bound
            if callbacks:
                self.data["sqlite_vm_queries_with_progress"] += 1
            current_min = self.data["sqlite_vm_per_query_lower_bound_min"]
            if current_min is None or lower_bound < current_min:
                self.data["sqlite_vm_per_query_lower_bound_min"] = lower_bound
            self.data["sqlite_vm_per_query_lower_bound_max"] = max(
                self.data["sqlite_vm_per_query_lower_bound_max"], lower_bound
            )

            # Retain only the largest bounded samples.  ``-sequence`` makes an
            # earlier query win deterministic ties without retaining every
            # request from a large N+1 workload.
            entry = (
                callback_quanta,
                -sequence,
                connection_id,
                request_id,
                outcome,
                callbacks,
                lower_bound,
                upper_bound_exclusive,
            )
            if len(self._vm_top_queries) < MAX_VM_TOP_QUERY_SAMPLES:
                heapq.heappush(self._vm_top_queries, entry)
            elif entry[:2] > self._vm_top_queries[0][:2]:
                heapq.heapreplace(self._vm_top_queries, entry)

    def snapshot(
        self,
        *,
        active_handlers: int,
        retained_handler_threads: int,
        database_sha256_after: str,
    ) -> dict:
        with self.lock:
            result = dict(self.data)
            result["error_types"] = dict(result["error_types"])
            result["active_handlers_at_stop"] = active_handlers
            result["retained_handler_threads_at_stop"] = retained_handler_threads
            result["database_sha256_after"] = database_sha256_after
            # Stable verifier-facing aliases.  The descriptive names remain in
            # the evidence so their lower-bound semantics are explicit.
            result["vm_progress_callbacks"] = result[
                "sqlite_vm_progress_callbacks_total"
            ]
            result["vm_steps"] = result["sqlite_vm_steps_lower_bound_total"]
            result["sqlite_vm_top_queries"] = [
                {
                    "sequence": -entry[1],
                    "connection_id": entry[2],
                    "request_id": entry[3],
                    "outcome": entry[4],
                    "progress_callbacks": entry[5],
                    "callback_quanta": entry[0],
                    "steps_lower_bound": entry[6],
                    "steps_upper_bound_exclusive": entry[7],
                }
                for entry in sorted(
                    self._vm_top_queries,
                    key=lambda item: (-item[0], -item[1]),
                )
            ]
            return result


class _PolicyDenied(sqlite3.DatabaseError):
    pass


def _open_read_only_database(path: str, stop_event: threading.Event):
    connection = sqlite3.connect(
        f"file:{path}?mode=ro&immutable=1",
        uri=True,
        check_same_thread=False,
    )
    connection.enable_load_extension(False)
    connection.execute("PRAGMA query_only = ON")
    # RLIMIT_FSIZE is zero so the meter can never create a persistent artifact.
    # Force legitimate SQLite sort/join temporaries into the service's separately
    # bounded address space; otherwise Linux may surface a false "disk I/O error"
    # for a read-only query whose plan spills a temporary B-tree.
    connection.execute("PRAGMA temp_store = MEMORY")
    if hasattr(connection, "setlimit"):
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16 * 1024 * 1024)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 256 * 1024)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 256)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 100)
        connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, MAX_PARAMETERS)

    progress_state = {"deadline": 0.0, "callbacks": 0}

    def authorize(action, arg1, arg2, database_name, trigger_name):
        if action == sqlite3.SQLITE_FUNCTION:
            function_name = (arg2 or arg1 or "").lower()
            if function_name in _DENIED_FUNCTIONS:
                return sqlite3.SQLITE_DENY
        if action not in _ALLOWED_AUTHORIZER_ACTIONS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def progress():
        progress_state["callbacks"] += 1
        if stop_event.is_set() or time.monotonic() > progress_state["deadline"]:
            return 1
        return 0

    connection.set_authorizer(authorize)
    connection.set_progress_handler(progress, SQLITE_VM_PROGRESS_STEPS)
    return connection, progress_state


def _encode_response(payload: dict) -> bytes:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise ValueError("database response exceeds the service byte limit")
    return encoded


def _error_response(request_id, error_type: str, message: str) -> bytes:
    return _encode_response(
        {
            "ok": False,
            "request_id": request_id,
            "error_type": error_type,
            "error": message[:500],
        }
    )


def _validate_request(raw: Any, previous_request_id: int):
    if not isinstance(raw, dict) or set(raw) != {"request_id", "sql", "params"}:
        raise _PolicyDenied("request schema is invalid")
    request_id = raw["request_id"]
    if type(request_id) is not int or request_id <= previous_request_id:
        raise _PolicyDenied("request_id must be a monotonically increasing integer")
    sql = raw["sql"]
    params = raw["params"]
    if not isinstance(sql, str) or not sql.strip():
        raise _PolicyDenied("sql must be a non-empty string")
    if len(sql.encode("utf-8")) > 256 * 1024:
        raise _PolicyDenied("sql exceeds the service limit")
    if not isinstance(params, list) or len(params) > MAX_PARAMETERS:
        raise _PolicyDenied("params must be a bounded list")
    for value in params:
        if value is not None and type(value) not in (str, int, float, bool):
            raise _PolicyDenied("only scalar JSON SQL parameters are supported")
        if isinstance(value, float) and not math.isfinite(value):
            raise _PolicyDenied("non-finite SQL parameter")
    return request_id, sql, params


def _handle_client(
    client: socket.socket,
    database_path: str,
    metrics: _SharedMetrics,
    stop_event: threading.Event,
    query_slots: threading.BoundedSemaphore,
) -> None:
    connection_id = metrics.connection_opened()
    previous_request_id = 0
    reader = client.makefile("rb")
    writer = client.makefile("wb")
    connection = None
    try:
        connection, progress_state = _open_read_only_database(
            database_path, stop_event
        )
        while not stop_event.is_set():
            line = reader.readline(MAX_REQUEST_BYTES + 1)
            if not line:
                break
            request_bytes = len(line)
            if not metrics.request_started(request_bytes):
                request_id_for_denial = None
                try:
                    raw_for_denial = json.loads(line)
                    if isinstance(raw_for_denial, dict):
                        request_id_for_denial = raw_for_denial.get("request_id")
                except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                    pass
                response = _error_response(
                    request_id_for_denial,
                    "PolicyDenied",
                    "total database request limit reached",
                )
                response_bytes = 0
                try:
                    writer.write(response)
                    writer.flush()
                    response_bytes = len(response)
                finally:
                    metrics.request_limit_rejection_sent(response_bytes)
                break
            request_id = None
            policy_denial = False
            sqlite_started = False
            sqlite_succeeded = False
            query_slot_acquired = False
            try:
                if len(line) > MAX_REQUEST_BYTES:
                    raise _PolicyDenied("database request exceeds the service byte limit")
                raw = json.loads(line)
                request_id, sql, params = _validate_request(raw, previous_request_id)
                previous_request_id = request_id
                query_slot_acquired = query_slots.acquire(
                    timeout=QUERY_TIMEOUT_SECONDS
                )
                if not query_slot_acquired:
                    raise _PolicyDenied(
                        "query concurrency wait exceeds the service limit"
                    )
                progress_state["callbacks"] = 0
                progress_state["deadline"] = (
                    time.monotonic() + QUERY_TIMEOUT_SECONDS
                )
                sqlite_started = True
                cursor = connection.execute(sql, params)
                columns = [item[0] for item in (cursor.description or ())]
                rows = []
                cell_count = 0
                estimated_response_bytes = len(
                    _encode_response(
                        {
                            "ok": True,
                            "request_id": request_id,
                            "columns": columns,
                            "rows": [],
                        }
                    )
                )
                while True:
                    batch = cursor.fetchmany(2048)
                    if not batch:
                        break
                    if len(rows) + len(batch) > MAX_ROWS_PER_REQUEST:
                        raise _PolicyDenied("query exceeds the service row limit")
                    for row in batch:
                        safe_row = [_safe_json_value(value) for value in row]
                        cell_count += len(safe_row)
                        if cell_count > MAX_CELLS_PER_REQUEST:
                            raise _PolicyDenied(
                                "query exceeds the service cell limit"
                            )
                        encoded_row = json.dumps(
                            safe_row,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            allow_nan=False,
                        ).encode("utf-8")
                        estimated_response_bytes += len(encoded_row) + bool(rows)
                        if estimated_response_bytes > MAX_RESPONSE_BYTES:
                            raise _PolicyDenied(
                                "database response exceeds the service byte limit"
                            )
                        rows.append(safe_row)
                response = _encode_response(
                    {
                        "ok": True,
                        "request_id": request_id,
                        "columns": columns,
                        "rows": rows,
                    }
                )
                writer.write(response)
                writer.flush()
                metrics.request_succeeded(len(rows), len(response))
                sqlite_succeeded = True
            except _PolicyDenied as exc:
                policy_denial = True
                response = _error_response(request_id, "PolicyDenied", str(exc))
                writer.write(response)
                writer.flush()
                metrics.request_failed(
                    "PolicyDenied", len(response), policy_denial=policy_denial
                )
            except sqlite3.DatabaseError as exc:
                message = str(exc)
                policy_denial = (
                    "not authorized" in message.lower()
                    or _is_request_resource_error(message)
                )
                integrity_failure = (
                    not policy_denial
                    and any(
                        fragment in message.lower()
                        for fragment in _INTEGRITY_ERROR_FRAGMENTS
                    )
                )
                error_type = "PolicyDenied" if policy_denial else type(exc).__name__
                response = _error_response(request_id, error_type, message)
                writer.write(response)
                writer.flush()
                metrics.request_failed(
                    error_type,
                    len(response),
                    policy_denial=policy_denial,
                    integrity_failure=integrity_failure,
                )
            except (
                UnicodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
                MemoryError,
                OverflowError,
            ) as exc:
                message = (
                    "query exceeded the service memory limit"
                    if isinstance(exc, MemoryError)
                    else str(exc)
                )
                policy_denial = sqlite_started and (
                    isinstance(exc, (MemoryError, OverflowError))
                    or _is_request_resource_error(message)
                )
                error_type = "PolicyDenied" if policy_denial else type(exc).__name__
                response = _error_response(request_id, error_type, message)
                writer.write(response)
                writer.flush()
                metrics.request_failed(
                    error_type,
                    len(response),
                    policy_denial=policy_denial,
                )
            finally:
                if sqlite_started:
                    metrics.sqlite_query_finished(
                        connection_id,
                        request_id,
                        progress_state["callbacks"],
                        succeeded=sqlite_succeeded,
                    )
                if query_slot_acquired:
                    query_slots.release()
    except (BrokenPipeError, ConnectionError, OSError):
        pass
    finally:
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass
        for stream in (writer, reader):
            try:
                stream.close()
            except OSError:
                pass
        try:
            client.close()
        except OSError:
            pass
        metrics.connection_closed()


def _reject_client_connection(
    client: socket.socket,
    metrics: _SharedMetrics,
    *,
    reason: str,
    message: str,
    policy_denial: bool,
    integrity_failure: bool = False,
) -> None:
    """Reject one accepted socket without allocating a handler thread."""

    error_type = "PolicyDenied" if policy_denial else "ServiceUnavailable"
    response = _error_response(None, error_type, message)
    response_bytes = 0
    try:
        # A peer that never reads must not stall the accept loop.  The denial is
        # small enough for a fresh Unix-socket send buffer in normal operation;
        # if the non-blocking send still fails, the server-owned counter remains
        # authoritative and the socket is closed immediately.
        client.setblocking(False)
        response_bytes = client.send(response)
    except (BlockingIOError, BrokenPipeError, ConnectionError, OSError):
        response_bytes = 0
    finally:
        try:
            client.close()
        except OSError:
            pass
        metrics.connection_rejected(
            reason,
            response_bytes,
            policy_denial=policy_denial,
            integrity_failure=integrity_failure,
        )


def _service_main(
    control,
    database_path: str,
    socket_path: str,
    attempt_id: str,
    expected_database_sha256: str,
    drop_privileges: bool,
    uid: int,
    gid: int,
    max_active_connections: int,
    max_total_handler_connections: int,
) -> None:
    server = None
    clients: set[socket.socket] = set()
    threads: set[threading.Thread] = set()
    state_lock = threading.Lock()
    stop_event = threading.Event()
    query_slots = threading.BoundedSemaphore(MAX_CONCURRENT_QUERIES)
    handlers_admitted = 0
    try:
        if drop_privileges:
            _drop_service_identity(uid, gid)
        actual_digest = _sha256(database_path)
        if actual_digest != expected_database_sha256:
            control.send(
                {
                    "type": "launch_error",
                    "attempt_id": attempt_id,
                    "error": "database digest mismatch before service start",
                }
            )
            return
        try:
            os.unlink(socket_path)
        except FileNotFoundError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(socket_path)
        os.chmod(socket_path, 0o666)
        server.listen(max_active_connections * 2)
        server.setblocking(False)
        metrics = _SharedMetrics(
            attempt_id,
            actual_digest,
            max_active_connections=max_active_connections,
            max_total_handler_connections=max_total_handler_connections,
        )
        control.send(
            {
                "type": "ready",
                "attempt_id": attempt_id,
                "database_sha256": actual_digest,
                "pid": os.getpid(),
                "uid": os.getuid(),
                "gid": os.getgid(),
                "max_active_connections": max_active_connections,
                "max_total_handler_connections": max_total_handler_connections,
            }
        )

        stopping = False
        while not stopping:
            readable, _, _ = select.select([server, control.fileno()], [], [], 0.25)
            if control.fileno() in readable:
                message = control.recv()
                if message == {"op": "stop", "attempt_id": attempt_id}:
                    stopping = True
            if server in readable:
                client, _ = server.accept()
                metrics.connection_seen()
                # On platforms where an accepted Unix socket inherits the
                # listener's non-blocking flag, a handler could observe EAGAIN
                # between two requests (or before a newly connected client has
                # written its first request) and incorrectly close the
                # connection.  Only the accept loop needs to be non-blocking;
                # each dedicated handler owns a blocking client socket.
                client.setblocking(True)
                denial_reason = None
                with state_lock:
                    if len(clients) >= max_active_connections:
                        denial_reason = "active_limit"
                    elif handlers_admitted >= max_total_handler_connections:
                        denial_reason = "total_limit"
                    else:
                        handlers_admitted += 1
                        clients.add(client)

                if denial_reason is not None:
                    _reject_client_connection(
                        client,
                        metrics,
                        reason=denial_reason,
                        message=(
                            "active database connection limit reached"
                            if denial_reason == "active_limit"
                            else "total database connection limit reached"
                        ),
                        policy_denial=True,
                    )
                    continue

                thread_holder: dict[str, threading.Thread] = {}

                def run_client(sock=client, holder=thread_holder):
                    try:
                        _handle_client(
                            sock,
                            database_path,
                            metrics,
                            stop_event,
                            query_slots,
                        )
                    except BaseException as exc:
                        # A request-path exception that escaped the typed handler
                        # means observer evidence may be incomplete.  Preserve that
                        # fact in the parent-bound report instead of silently losing
                        # a daemon thread and misgrading the candidate.
                        metrics.handler_runtime_failed(type(exc).__name__)
                        stop_event.set()
                    finally:
                        with state_lock:
                            clients.discard(sock)
                            thread = holder.get("thread")
                            if thread is not None:
                                threads.discard(thread)

                try:
                    thread = threading.Thread(target=run_client, daemon=True)
                except Exception:
                    with state_lock:
                        clients.discard(client)
                    metrics.handler_thread_start_failed()
                    _reject_client_connection(
                        client,
                        metrics,
                        reason="handler_start",
                        message="database handler could not be allocated",
                        policy_denial=False,
                        integrity_failure=True,
                    )
                    continue
                thread_holder["thread"] = thread
                with state_lock:
                    threads.add(thread)
                    retained_threads = len(threads)
                metrics.handler_thread_reserved(retained_threads)
                try:
                    thread.start()
                except Exception:
                    with state_lock:
                        threads.discard(thread)
                        clients.discard(client)
                    metrics.handler_thread_start_failed()
                    _reject_client_connection(
                        client,
                        metrics,
                        reason="handler_start",
                        message="database handler could not start",
                        policy_denial=False,
                        integrity_failure=True,
                    )
                else:
                    metrics.handler_thread_started()

        stop_event.set()
        if server is not None:
            server.close()
            server = None
        with state_lock:
            clients_at_stop = list(clients)
            threads_at_stop = list(threads)
        for client in clients_at_stop:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
        for thread in threads_at_stop:
            thread.join(timeout=2.0)
        active = sum(thread.is_alive() for thread in threads_at_stop)
        with state_lock:
            retained = len(threads)
        if active or retained:
            metrics.shutdown_not_quiescent(active, retained)
        after_digest = _sha256(database_path)
        control.send(
            {
                "type": "final",
                "attempt_id": attempt_id,
                "metrics": metrics.snapshot(
                    active_handlers=active,
                    retained_handler_threads=retained,
                    database_sha256_after=after_digest,
                ),
            }
        )
    except BaseException as exc:
        try:
            control.send(
                {
                    "type": "service_error",
                    "attempt_id": attempt_id,
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                }
            )
        except BaseException:
            pass
    finally:
        stop_event.set()
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        with state_lock:
            remaining_clients = list(clients)
        for client in remaining_clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
        try:
            os.unlink(socket_path)
        except OSError:
            pass
        try:
            control.close()
        except OSError:
            pass


class MeteredSQLiteService:
    """Parent-side lifecycle wrapper for one hidden-database measurement."""

    def __init__(
        self,
        database_path: str,
        socket_path: str,
        attempt_id: str,
        database_sha256: str,
        *,
        drop_privileges: bool,
        uid: int,
        gid: int,
        max_active_connections: int = MAX_ACTIVE_CONNECTIONS,
        max_total_handler_connections: int = MAX_TOTAL_HANDLER_CONNECTIONS,
    ):
        if (
            type(max_active_connections) is not int
            or max_active_connections < 1
        ):
            raise ValueError("max_active_connections must be a positive integer")
        if (
            type(max_total_handler_connections) is not int
            or max_total_handler_connections < max_active_connections
        ):
            raise ValueError(
                "max_total_handler_connections must be an integer greater than "
                "or equal to max_active_connections"
            )
        self.database_path = database_path
        self.socket_path = socket_path
        self.attempt_id = attempt_id
        self.database_sha256 = database_sha256
        self.drop_privileges = drop_privileges
        self.uid = uid
        self.gid = gid
        self.max_active_connections = max_active_connections
        self.max_total_handler_connections = max_total_handler_connections
        self._control = None
        self._process = None
        self.ready = None

    def start(self, timeout: float = 15.0) -> dict:
        context = multiprocessing.get_context("fork")
        parent_control, child_control = context.Pipe(duplex=True)
        process = context.Process(
            target=_service_main,
            args=(
                child_control,
                self.database_path,
                self.socket_path,
                self.attempt_id,
                self.database_sha256,
                self.drop_privileges,
                self.uid,
                self.gid,
                self.max_active_connections,
                self.max_total_handler_connections,
            ),
            name=f"f01-meter-{self.attempt_id[:8]}",
        )
        process.start()
        child_control.close()
        self._control = parent_control
        self._process = process
        if not parent_control.poll(timeout):
            self.abort()
            raise RuntimeError("meter service did not become ready")
        message = parent_control.recv()
        if (
            message.get("type") != "ready"
            or message.get("attempt_id") != self.attempt_id
            or message.get("database_sha256") != self.database_sha256
        ):
            self.abort()
            raise RuntimeError(f"meter service launch failed: {message}")
        self.ready = message
        return message

    def stop(self, timeout: float = 20.0) -> dict:
        if self._control is None or self._process is None:
            raise RuntimeError("meter service was not started")
        if not self._process.is_alive():
            exitcode = self._process.exitcode
            self.abort()
            raise RuntimeError(
                f"meter service exited before final evidence (exitcode={exitcode})"
            )
        self._control.send({"op": "stop", "attempt_id": self.attempt_id})
        if not self._control.poll(timeout):
            self.abort()
            raise RuntimeError("meter service did not return final evidence")
        message = self._control.recv()
        self._process.join(timeout=5.0)
        if self._process.is_alive():
            self.abort()
            raise RuntimeError("meter service did not exit after final evidence")
        if (
            message.get("type") != "final"
            or message.get("attempt_id") != self.attempt_id
            or not isinstance(message.get("metrics"), dict)
        ):
            self.abort()
            raise RuntimeError(f"meter service final evidence is invalid: {message}")
        metrics = message["metrics"]
        if (
            metrics.get("attempt_id") != self.attempt_id
            or metrics.get("database_sha256") != self.database_sha256
            or metrics.get("database_sha256_after") != self.database_sha256
        ):
            raise RuntimeError("meter service evidence binding failed")
        self._control.close()
        self._control = None
        self._process = None
        return metrics

    def abort(self) -> None:
        process = self._process
        control = self._control
        if process is not None:
            if process.is_alive():
                process.terminate()
                process.join(timeout=3.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=3.0)
        if control is not None:
            try:
                control.close()
            except OSError:
                pass
        self._control = None
        self._process = None
