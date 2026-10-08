"""Run the statement export from a given source tree in THIS fresh process,
counting SQL statements and timing the job.

    python3 -I run_counted.py --src /app --db X.db --month 2026-03 --out out.json --result result.json

Runs the job through its command-line entry point (the contract the task pins),
so any internal refactor is fine as long as `python -m ledgerly.report` still works.
"""
import argparse
import _sqlite3
import gc
import json
import os
import resource
import sqlite3
import sys
import time

_perf_counter = time.perf_counter  # captured before any task code can monkeypatch it
_gc_get_objects = gc.get_objects
_getrusage = resource.getrusage
_RUSAGE_CHILDREN = resource.RUSAGE_CHILDREN
_open_file = open
_json_dump = json.dump
_fsync = os.fsync
_exit_immediately = os._exit

parser = argparse.ArgumentParser()
parser.add_argument("--src", required=True)
parser.add_argument("--db", required=True)
parser.add_argument("--month", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--result", required=True)
args = parser.parse_args()

sys.path.insert(0, args.src)

statements_executed = 0
rows_delivered = 0
_original_connect = sqlite3.connect
_OriginalConnection = sqlite3.Connection
_OriginalCursor = sqlite3.Cursor
_original_set_trace_callback = _OriginalConnection.set_trace_callback
_cursor_row_factory_descriptor = _OriginalCursor.row_factory
_dbapi2 = sqlite3.dbapi2
_counted_connections = {}
_audited_connections = {}
_child_events = []


def _audit(event: str, event_args: tuple) -> None:
    # The sqlite handle event fires before Connection.__init__ has finished on Python
    # 3.12, so retain the object here and validate it only after the workload returns.
    if event == "sqlite3.connect/handle" and event_args:
        handle = event_args[0]
        _audited_connections.setdefault(id(handle), handle)
    elif event in {"subprocess.Popen", "os.fork", "os.forkpty", "os.posix_spawn", "os.system"}:
        _child_events.append(event)


sys.addaudithook(_audit)


def _count(_statement: str) -> None:
    global statements_executed
    statements_executed += 1


def _count_rows(count: int) -> None:
    """Record rows that SQLite has actually returned to task code.

    This deliberately meters the cursor boundary rather than estimating from a
    query plan or prescribing SQL text.  Each public retrieval operation below
    delegates straight to the native cursor exactly once.  A verifier-owned row
    factory wrapper accounts for each raw row before preserving the cursor's
    original factory result.  This remains exact even when a valid custom row
    factory returns ``None``, which is indistinguishable from exhaustion at the
    public ``fetchone`` boundary.
    """
    global rows_delivered
    rows_delivered += count


def _restore_counter(conn) -> None:
    _original_set_trace_callback(conn, _count)


class CountedCursor(sqlite3.Cursor):
    """Cursor that restores statement tracing and meters rows returned to Python."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._meter_original_row_factory = None
        self._meter_row_factory = None

    def _install_row_meter(self, original_factory) -> None:
        def metered_factory(cursor, row):
            _count_rows(1)
            if original_factory is None:
                return row
            return original_factory(cursor, row)

        self._meter_original_row_factory = original_factory
        self._meter_row_factory = metered_factory
        _cursor_row_factory_descriptor.__set__(self, metered_factory)

    def _adopt_native_row_factory(self) -> None:
        # Connection.cursor copies Connection.row_factory only after the custom
        # cursor constructor returns.  CountedConnection calls this once that
        # copy is complete so sqlite3.Row and custom factories remain unchanged.
        self._install_row_meter(_cursor_row_factory_descriptor.__get__(self, type(self)))

    def _ensure_row_meter(self) -> None:
        native_factory = _cursor_row_factory_descriptor.__get__(self, type(self))
        if native_factory is not self._meter_row_factory:
            # A caller used the native descriptor directly.  Preserve the newly
            # requested semantics but put the verifier meter back around it.
            self._install_row_meter(native_factory)

    @property
    def row_factory(self):
        return self._meter_original_row_factory

    @row_factory.setter
    def row_factory(self, factory):
        self._install_row_meter(factory)

    def execute(self, *a, **kw):
        _restore_counter(self.connection)
        return super().execute(*a, **kw)

    def executemany(self, *a, **kw):
        _restore_counter(self.connection)
        return super().executemany(*a, **kw)

    def executescript(self, *a, **kw):
        _restore_counter(self.connection)
        return super().executescript(*a, **kw)

    def fetchone(self):
        self._ensure_row_meter()
        return super().fetchone()

    def fetchmany(self, *a, **kw):
        self._ensure_row_meter()
        return super().fetchmany(*a, **kw)

    def fetchall(self):
        self._ensure_row_meter()
        return super().fetchall()

    def __iter__(self):
        return self

    def __next__(self):
        self._ensure_row_meter()
        return super().__next__()


class CountedConnection(_OriginalConnection):
    """A connection that installs the counter itself and will not let task code remove it."""

    def __init__(self, *a, **kw):
        # Register before super().__init__: sqlite3.connect/handle is audited during
        # that call, while the native Connection is not safe to operate on yet.
        _counted_connections[id(self)] = self
        super().__init__(*a, **kw)
        _restore_counter(self)

    def set_trace_callback(self, _trace_callback):
        # The verifier owns the callback for the lifetime of this process.
        return None

    def cursor(self, *a, **kw):
        _restore_counter(self)
        # A caller-supplied cursor factory must not opt out of restoring the trace.
        cursor = super().cursor(factory=CountedCursor)
        cursor._adopt_native_row_factory()
        return cursor

    def execute(self, *a, **kw):
        _restore_counter(self)
        # sqlite3.Connection.execute normally creates a native Cursor directly,
        # bypassing an overridden ``cursor`` method.  Route the convenience API
        # through CountedCursor so its result rows cross the same meter.
        return self.cursor().execute(*a, **kw)

    def executemany(self, *a, **kw):
        _restore_counter(self)
        return self.cursor().executemany(*a, **kw)

    def executescript(self, *a, **kw):
        _restore_counter(self)
        return self.cursor().executescript(*a, **kw)

    def commit(self):
        _restore_counter(self)
        return super().commit()

    def rollback(self):
        _restore_counter(self)
        return super().rollback()


def _counting_connect(*a, **kw):
    # sqlite3.connect accepts factory as its sixth positional parameter. Replace a
    # caller-supplied factory instead of allowing it to opt out of instrumentation.
    positional = list(a)
    if len(positional) > 5:
        positional[5] = CountedConnection
        kw.pop("factory", None)
    else:
        kw["factory"] = CountedConnection
    return _original_connect(*positional, **kw)


sqlite3.connect = _counting_connect
_dbapi2.connect = _counting_connect
_sqlite3.connect = _counting_connect
sqlite3.Connection = CountedConnection
_dbapi2.Connection = CountedConnection
_sqlite3.Connection = CountedConnection

_expected_bindings = (
    (sqlite3, "connect", _counting_connect),
    (_dbapi2, "connect", _counting_connect),
    (_sqlite3, "connect", _counting_connect),
    (sqlite3, "Connection", CountedConnection),
    (_dbapi2, "Connection", CountedConnection),
    (_sqlite3, "Connection", CountedConnection),
)


def _child_cpu_seconds() -> float:
    usage = _getrusage(_RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def _peak_rss() -> tuple[int, str, int]:
    """Return ru_maxrss as (raw integer, raw unit, normalized bytes).

    Python exposes bytes on macOS and KiB on Linux and the other supported
    verifier images.  Keeping both forms makes the conversion auditable while
    ``peak_rss_bytes`` remains directly comparable across those platforms.
    """
    raw = int(_getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return raw, "bytes", raw
    return raw, "KiB", raw * 1024


def _guard_failures(child_cpu_delta: float) -> tuple[list[str], int]:
    registered = set(_counted_connections)
    seen = dict(_audited_connections)
    # The audit hook is the primary inventory and keeps handles alive. The GC scan is
    # an independent backstop for a constructor path that does not emit the event.
    for obj in _gc_get_objects():
        if isinstance(obj, _OriginalConnection):
            seen.setdefault(id(obj), obj)

    failures = []
    if _child_events or child_cpu_delta > 0.0:
        failures.append("subprocess_used")
    if any(getattr(module, name, None) is not expected for module, name, expected in _expected_bindings):
        failures.append("patch_removed")
    if set(seen) - registered:
        failures.append("uncounted_queries")
    return failures, len(seen)


child_cpu_start = _child_cpu_seconds()
result = {
    "ok": False,
    "queries": None,
    "rows_delivered": None,
    "seconds": None,
    "error": None,
    "guard_failure": None,
    "connections_opened": 0,
    "child_cpu_seconds": None,
    "peak_rss_raw": None,
    "peak_rss_raw_unit": None,
    "peak_rss_bytes": None,
}
try:
    from ledgerly.report import main  # noqa: E402

    t0 = _perf_counter()
    try:
        rc = main(["--db", args.db, "--month", args.month, "--out", args.out])
    except SystemExit as exc:  # a CLI that calls sys.exit(0) is fine
        rc = exc.code or 0
    seconds = _perf_counter() - t0
    if rc not in (0, None):
        raise RuntimeError(f"main returned {rc}")
    result.update(
        ok=True,
        queries=int(statements_executed),
        rows_delivered=int(rows_delivered),
        seconds=seconds,
    )
except BaseException as exc:  # noqa: BLE001 — report anything, including SystemExit/KeyboardInterrupt
    result["error"] = f"{type(exc).__name__}: {exc}"[:2000]

child_cpu_delta = max(0.0, _child_cpu_seconds() - child_cpu_start)
failures, connections_opened = _guard_failures(child_cpu_delta)
peak_rss_raw, peak_rss_raw_unit, peak_rss_bytes = _peak_rss()
result.update(
    guard_failure=failures[0] if failures else None,
    connections_opened=int(connections_opened),
    child_cpu_seconds=round(child_cpu_delta, 6),
    peak_rss_raw=peak_rss_raw,
    peak_rss_raw_unit=peak_rss_raw_unit,
    peak_rss_bytes=peak_rss_bytes,
)

try:
    with _open_file(args.result, "w", encoding="utf-8") as fh:
        _json_dump(result, fh)
        fh.flush()
        _fsync(fh.fileno())
except BaseException:
    # Never run task-controlled atexit handlers after a partial/failed trusted
    # result write.  The verifier will observe the non-zero runner status.
    _exit_immediately(70)

# Imported task code may register atexit handlers.  A normal interpreter exit
# would run them after the trusted result is written, allowing the task to
# replace the metrics file.  Commit above, then terminate without handlers.
_exit_immediately(0)
