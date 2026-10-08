#!/usr/bin/env python3
"""Agent-visible, read-only SQLite service with diagnostic accounting.

This is a development reproduction aid, not part of the trusted grader.  It
speaks the same ``metered+unix://`` JSON-lines protocol as the hidden database
service so the visible workload exercises the same application boundary.  The
metrics it prints are intentionally diagnostic: code in the task environment
can observe or modify this process and therefore they are never grading
evidence.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import select
import signal
import socket
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_ROWS_PER_REQUEST = 500_000
MAX_CELLS_PER_REQUEST = 3_000_000
MAX_PARAMETERS = 50_000
MAX_TOTAL_REQUESTS = 1_000_000
MAX_CONCURRENT_QUERIES = 1
MAX_ACTIVE_CONNECTIONS = 4
MAX_TOTAL_HANDLER_CONNECTIONS = 64
QUERY_TIMEOUT_SECONDS = 15.0
SQLITE_VM_PROGRESS_STEPS = 10_000

_ALLOWED_AUTHORIZER_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
}
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    _ALLOWED_AUTHORIZER_ACTIONS.add(sqlite3.SQLITE_RECURSIVE)

_DENIED_FUNCTIONS = {"load_extension", "readfile", "writefile"}


def _json_value(value: Any):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite SQLite value")
        return value
    if isinstance(value, bytes):
        return {"__bytes_b64__": base64.b64encode(value).decode("ascii")}
    raise ValueError(f"unsupported SQLite value type: {type(value).__name__}")


def _encode(payload: dict) -> bytes:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise ValueError("database response exceeds the service byte limit")
    return encoded


def _error(request_id, error_type: str, message: str) -> bytes:
    return _encode(
        {
            "ok": False,
            "request_id": request_id,
            "error_type": error_type,
            "error": message[:500],
        }
    )


class PolicyDenied(sqlite3.DatabaseError):
    """A request outside the visible service's read-only SQL policy."""


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._active_connections = 0
        self._started = time.monotonic()
        self._data = {
            "protocol": "metered+unix-v1",
            "trusted_grader_evidence": False,
            "connections_accepted": 0,
            "peak_concurrent_connections": 0,
            "requests_total": 0,
            "requests_rejected_total_limit": 0,
            "connections_rejected": 0,
            "connections_rejected_active_limit": 0,
            "connections_rejected_total_limit": 0,
            "queries_succeeded": 0,
            "queries_failed": 0,
            "policy_denials": 0,
            "rows_delivered": 0,
            "request_bytes": 0,
            "response_bytes": 0,
            "error_types": Counter(),
        }

    def opened(self) -> None:
        with self._lock:
            self._active_connections += 1
            self._data["connections_accepted"] += 1
            self._data["peak_concurrent_connections"] = max(
                self._data["peak_concurrent_connections"],
                self._active_connections,
            )

    def closed(self) -> None:
        with self._lock:
            self._active_connections = max(0, self._active_connections - 1)

    def requested(self, byte_count: int) -> bool:
        with self._lock:
            if self._data["requests_total"] >= MAX_TOTAL_REQUESTS:
                self._data["requests_rejected_total_limit"] += 1
                self._data["policy_denials"] += 1
                self._data["error_types"]["PolicyDenied"] += 1
                return False
            self._data["requests_total"] += 1
            self._data["request_bytes"] += byte_count
            return True

    def rejected(self, reason: str, byte_count: int) -> None:
        with self._lock:
            self._data["connections_rejected"] += 1
            self._data[f"connections_rejected_{reason}"] += 1
            self._data["policy_denials"] += 1
            self._data["response_bytes"] += byte_count
            self._data["error_types"]["PolicyDenied"] += 1

    def succeeded(self, row_count: int, byte_count: int) -> None:
        with self._lock:
            self._data["queries_succeeded"] += 1
            self._data["rows_delivered"] += row_count
            self._data["response_bytes"] += byte_count

    def failed(self, error_type: str, byte_count: int, policy_denial: bool) -> None:
        with self._lock:
            self._data["queries_failed"] += 1
            self._data["response_bytes"] += byte_count
            self._data["policy_denials"] += int(policy_denial)
            self._data["error_types"][error_type] += 1

    def snapshot(self) -> dict:
        with self._lock:
            result = dict(self._data)
            result["error_types"] = dict(result["error_types"])
            result["active_connections_at_stop"] = self._active_connections
            result["service_elapsed_seconds"] = round(
                time.monotonic() - self._started, 6
            )
            return result


def _validate_request(raw: Any, previous_request_id: int):
    if not isinstance(raw, dict) or set(raw) != {"request_id", "sql", "params"}:
        raise PolicyDenied("request schema is invalid")
    request_id = raw["request_id"]
    if type(request_id) is not int or request_id <= previous_request_id:
        raise PolicyDenied("request_id must be a monotonically increasing integer")
    sql = raw["sql"]
    params = raw["params"]
    if not isinstance(sql, str) or not sql.strip():
        raise PolicyDenied("sql must be a non-empty string")
    if len(sql.encode("utf-8")) > 256 * 1024:
        raise PolicyDenied("sql exceeds the service limit")
    if not isinstance(params, list) or len(params) > MAX_PARAMETERS:
        raise PolicyDenied("params must be a bounded list")
    for value in params:
        if value is not None and type(value) not in (str, int, float, bool):
            raise PolicyDenied("only scalar JSON SQL parameters are supported")
        if isinstance(value, float) and not math.isfinite(value):
            raise PolicyDenied("non-finite SQL parameter")
    return request_id, sql, params


def _open_database(database_path: str, stop_event: threading.Event):
    connection = sqlite3.connect(
        f"file:{database_path}?mode=ro&immutable=1",
        uri=True,
        check_same_thread=False,
    )
    connection.enable_load_extension(False)
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA temp_store = MEMORY")
    if hasattr(connection, "setlimit"):
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16 * 1024 * 1024)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 256 * 1024)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 256)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 100)
        connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, MAX_PARAMETERS)

    deadline = [0.0]

    def authorize(action, arg1, arg2, database_name, trigger_name):
        if action == sqlite3.SQLITE_FUNCTION:
            function_name = (arg2 or arg1 or "").lower()
            if function_name in _DENIED_FUNCTIONS:
                return sqlite3.SQLITE_DENY
        if action not in _ALLOWED_AUTHORIZER_ACTIONS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def progress():
        return int(stop_event.is_set() or time.monotonic() > deadline[0])

    connection.set_authorizer(authorize)
    connection.set_progress_handler(progress, SQLITE_VM_PROGRESS_STEPS)
    return connection, deadline


def _handle_client(
    client: socket.socket,
    database_path: str,
    metrics: Metrics,
    stop_event: threading.Event,
    query_slots: threading.BoundedSemaphore,
) -> None:
    metrics.opened()
    previous_request_id = 0
    reader = client.makefile("rb")
    writer = client.makefile("wb")
    connection = None
    try:
        connection, deadline = _open_database(database_path, stop_event)
        while not stop_event.is_set():
            line = reader.readline(MAX_REQUEST_BYTES + 1)
            if not line:
                break
            if not metrics.requested(len(line)):
                request_id = None
                try:
                    raw_for_denial = json.loads(line)
                    if isinstance(raw_for_denial, dict):
                        request_id = raw_for_denial.get("request_id")
                except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                    pass
                response = _error(
                    request_id,
                    "PolicyDenied",
                    "total database request limit reached",
                )
                writer.write(response)
                writer.flush()
                break
            request_id = None
            policy_denial = False
            query_slot_acquired = False
            try:
                if len(line) > MAX_REQUEST_BYTES:
                    raise PolicyDenied("database request exceeds the service byte limit")
                raw = json.loads(line)
                request_id, sql, params = _validate_request(
                    raw, previous_request_id
                )
                previous_request_id = request_id
                query_slot_acquired = query_slots.acquire(
                    timeout=QUERY_TIMEOUT_SECONDS
                )
                if not query_slot_acquired:
                    raise PolicyDenied(
                        "query concurrency wait exceeds the service limit"
                    )
                deadline[0] = time.monotonic() + QUERY_TIMEOUT_SECONDS
                cursor = connection.execute(sql, params)
                columns = [item[0] for item in (cursor.description or ())]
                rows = []
                cell_count = 0
                estimated_response_bytes = len(
                    _encode(
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
                        raise PolicyDenied("query exceeds the service row limit")
                    for row in batch:
                        safe_row = [_json_value(value) for value in row]
                        cell_count += len(safe_row)
                        if cell_count > MAX_CELLS_PER_REQUEST:
                            raise PolicyDenied(
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
                            raise PolicyDenied(
                                "database response exceeds the service byte limit"
                            )
                        rows.append(safe_row)
                response = _encode(
                    {
                        "ok": True,
                        "request_id": request_id,
                        "columns": columns,
                        "rows": rows,
                    }
                )
                writer.write(response)
                writer.flush()
                metrics.succeeded(len(rows), len(response))
            except PolicyDenied as exc:
                policy_denial = True
                response = _error(request_id, "PolicyDenied", str(exc))
                writer.write(response)
                writer.flush()
                metrics.failed("PolicyDenied", len(response), policy_denial)
            except sqlite3.DatabaseError as exc:
                message = str(exc)
                policy_denial = (
                    "not authorized" in message.lower()
                    or "interrupted" in message.lower()
                )
                error_type = "PolicyDenied" if policy_denial else type(exc).__name__
                response = _error(request_id, error_type, message)
                writer.write(response)
                writer.flush()
                metrics.failed(error_type, len(response), policy_denial)
            except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                response = _error(request_id, type(exc).__name__, str(exc))
                writer.write(response)
                writer.flush()
                metrics.failed(type(exc).__name__, len(response), policy_denial)
            finally:
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
        metrics.closed()


def serve(args) -> int:
    database_path = os.path.abspath(args.db)
    socket_path = os.path.abspath(args.socket)
    ready_path = os.path.abspath(args.ready_file)
    metrics_path = os.path.abspath(args.metrics_file)
    for path in (database_path,):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
    for path in (socket_path, ready_path, metrics_path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    stop_event = threading.Event()
    query_slots = threading.BoundedSemaphore(MAX_CONCURRENT_QUERIES)
    metrics = Metrics()
    clients: set[socket.socket] = set()
    clients_lock = threading.Lock()
    threads: list[threading.Thread] = []
    handlers_admitted = 0

    def request_stop(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(socket_path)
        os.chmod(socket_path, 0o600)
        server.listen(MAX_ACTIVE_CONNECTIONS * 2)
        server.setblocking(False)
        Path(ready_path).write_text(
            json.dumps({"protocol": "metered+unix-v1", "ready": True}) + "\n",
            encoding="utf-8",
        )
        print(
            "visible database service ready "
            "(diagnostic only; not trusted grader evidence)",
            flush=True,
        )
        while not stop_event.is_set():
            readable, _, _ = select.select([server], [], [], 0.20)
            if server not in readable:
                continue
            client, _ = server.accept()
            client.setblocking(True)
            denial_reason = None
            with clients_lock:
                if len(clients) >= MAX_ACTIVE_CONNECTIONS:
                    denial_reason = "active_limit"
                elif handlers_admitted >= MAX_TOTAL_HANDLER_CONNECTIONS:
                    denial_reason = "total_limit"
                else:
                    handlers_admitted += 1
                    clients.add(client)

            if denial_reason is not None:
                response = _error(
                    None,
                    "PolicyDenied",
                    (
                        "active database connection limit reached"
                        if denial_reason == "active_limit"
                        else "total database connection limit reached"
                    ),
                )
                response_bytes = 0
                try:
                    client.setblocking(False)
                    response_bytes = client.send(response)
                except (BlockingIOError, BrokenPipeError, ConnectionError, OSError):
                    pass
                finally:
                    client.close()
                    metrics.rejected(denial_reason, response_bytes)
                continue

            def run_client(sock=client):
                try:
                    _handle_client(
                        sock,
                        database_path,
                        metrics,
                        stop_event,
                        query_slots,
                    )
                finally:
                    with clients_lock:
                        clients.discard(sock)

            thread = threading.Thread(target=run_client, daemon=True)
            threads.append(thread)
            thread.start()
    finally:
        stop_event.set()
        server.close()
        with clients_lock:
            open_clients = list(clients)
        for client in open_clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
        for thread in threads:
            thread.join(timeout=2.0)
        snapshot = metrics.snapshot()
        Path(metrics_path).write_text(
            json.dumps(snapshot, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            "visible database diagnostics (not grader evidence): "
            + json.dumps(snapshot, sort_keys=True),
            flush=True,
        )
        for path in (socket_path, ready_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite database to serve read-only")
    parser.add_argument("--socket", required=True, help="absolute Unix socket path")
    parser.add_argument("--ready-file", required=True, help="startup readiness marker")
    parser.add_argument("--metrics-file", required=True, help="final diagnostic JSON")
    args = parser.parse_args(argv)
    if not os.path.isabs(args.socket):
        parser.error("--socket must be an absolute path")
    return args


if __name__ == "__main__":
    raise SystemExit(serve(parse_args()))
