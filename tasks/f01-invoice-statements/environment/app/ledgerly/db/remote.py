"""Small DB-API client for Ledgerly's read-only database service.

The production export talks to a hosted database.  The benchmark's visible and
hidden service processes expose the same read-only SQL request protocol over a
Unix-domain socket.  Keeping this transport behind `connect()` lets repository
code use the normal `execute()/fetch*` surface while the service, rather than
application code, owns request and transfer accounting.
"""
from __future__ import annotations

import json
import socket
import sqlite3
from collections.abc import Iterator, Sequence
from typing import Any

URL_PREFIX = "metered+unix://"
_MAX_MESSAGE_BYTES = 128 * 1024 * 1024


class RemoteDatabaseError(RuntimeError):
    """The database service rejected a request or could not complete it."""


class RemoteRow(Sequence):
    """A compact sqlite3.Row-compatible value used by the remote client."""

    __slots__ = ("_columns", "_values", "_index")

    def __init__(self, columns: Sequence[str], values: Sequence[Any]):
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._index = {name: index for index, name in enumerate(self._columns)}

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._index[key]]
        return self._values[key]

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def keys(self) -> list[str]:
        return list(self._columns)


class RemoteCursor:
    """Buffered read-only cursor for the subset Ledgerly uses."""

    def __init__(self, connection: "RemoteConnection"):
        self.connection = connection
        self.description = None
        self.rowcount = -1
        self._rows: list[Any] = []
        self._index = 0

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> "RemoteCursor":
        response = self.connection._query(sql, parameters)
        columns = response["columns"]
        raw_rows = response["rows"]
        self.description = [
            (name, None, None, None, None, None, None) for name in columns
        ]
        self._rows = [self._adapt_row(columns, values) for values in raw_rows]
        self._index = 0
        self.rowcount = len(self._rows)
        return self

    def _adapt_row(self, columns: Sequence[str], values: Sequence[Any]):
        factory = self.connection.row_factory
        if factory is None:
            return tuple(values)
        if factory is sqlite3.Row:
            return RemoteRow(columns, values)
        return factory(self, tuple(values))

    def fetchone(self):
        if self._index >= len(self._rows):
            return None
        value = self._rows[self._index]
        self._index += 1
        return value

    def fetchmany(self, size: int | None = None):
        count = self.arraysize if size is None else size
        start = self._index
        self._index = min(len(self._rows), start + count)
        return self._rows[start:self._index]

    def fetchall(self):
        start = self._index
        self._index = len(self._rows)
        return self._rows[start:]

    @property
    def arraysize(self) -> int:
        return 1

    def __iter__(self) -> "RemoteCursor":
        return self

    def __next__(self):
        value = self.fetchone()
        if value is None:
            raise StopIteration
        return value

    def close(self) -> None:
        self._rows = []
        self._index = 0


class RemoteConnection:
    """One persistent connection to the verifier-owned database service."""

    def __init__(self, socket_path: str, *, timeout: float = 120.0):
        self.socket_path = socket_path
        self.row_factory = sqlite3.Row
        self._request_id = 0
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.settimeout(timeout)
        self._socket.connect(socket_path)
        self._reader = self._socket.makefile("rb")
        self._writer = self._socket.makefile("wb")
        self._closed = False

    def cursor(self, *args, **kwargs) -> RemoteCursor:
        if args or kwargs:
            raise TypeError("remote cursor factories are not supported")
        self._ensure_open()
        return RemoteCursor(self)

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> RemoteCursor:
        return self.cursor().execute(sql, parameters)

    def _query(self, sql: str, parameters: Sequence[Any]) -> dict[str, Any]:
        self._ensure_open()
        self._request_id += 1
        request = {
            "request_id": self._request_id,
            "sql": sql,
            "params": list(parameters),
        }
        encoded = json.dumps(
            request, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8") + b"\n"
        if len(encoded) > _MAX_MESSAGE_BYTES:
            raise RemoteDatabaseError("database request is too large")
        self._writer.write(encoded)
        self._writer.flush()
        line = self._reader.readline(_MAX_MESSAGE_BYTES + 1)
        if not line:
            raise RemoteDatabaseError("database service closed the connection")
        if len(line) > _MAX_MESSAGE_BYTES:
            raise RemoteDatabaseError("database response is too large")
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RemoteDatabaseError("database service returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise RemoteDatabaseError("database service returned an invalid response")
        if response.get("request_id") != self._request_id:
            raise RemoteDatabaseError("database response did not match the request")
        if response.get("ok") is not True:
            kind = response.get("error_type", "DatabaseError")
            message = response.get("error", "request failed")
            raise RemoteDatabaseError(f"{kind}: {message}")
        if not isinstance(response.get("columns"), list) or not isinstance(
            response.get("rows"), list
        ):
            raise RemoteDatabaseError("database response schema is invalid")
        return response

    def _ensure_open(self) -> None:
        if self._closed:
            raise RemoteDatabaseError("database connection is closed")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for stream in (self._writer, self._reader):
            try:
                stream.close()
            except OSError:
                pass
        try:
            self._socket.close()
        except OSError:
            pass

    def commit(self) -> None:
        self._ensure_open()

    def rollback(self) -> None:
        self._ensure_open()

    def __enter__(self) -> "RemoteConnection":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def is_remote_url(path: str) -> bool:
    return path.startswith(URL_PREFIX)


def connect_remote(path: str) -> RemoteConnection:
    if not is_remote_url(path):
        raise ValueError(f"expected {URL_PREFIX!r} database URL")
    socket_path = path[len(URL_PREFIX):]
    if not socket_path.startswith("/"):
        raise ValueError("remote database URL must contain an absolute socket path")
    return RemoteConnection(socket_path)

