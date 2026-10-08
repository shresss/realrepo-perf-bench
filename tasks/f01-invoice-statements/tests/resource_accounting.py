"""Bounded Linux storage accounting for untrusted verifier children.

The task process can unlink a file while retaining an open descriptor, or open a
regular file outside its assigned working directory.  A directory walk alone
therefore is not a storage bound.  This module combines the bounded work-tree
walk with regular files referenced from every process owned by the task UID.

It is verifier-only code.  ``proc_root`` and ``pid_names`` exist so the scanner
can be exercised against deterministic fake proc trees in unit tests.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Iterable


_PROC_RACE_ERRNOS = {errno.ENOENT, errno.ESRCH, errno.ENOTDIR, errno.EBADF}


def _is_proc_race(exc: OSError) -> bool:
    return isinstance(exc, (FileNotFoundError, ProcessLookupError)) or (
        exc.errno in _PROC_RACE_ERRNOS
    )


def _size_pair(info: os.stat_result) -> tuple[int, int]:
    return (
        max(0, int(info.st_size)),
        max(0, int(getattr(info, "st_blocks", 0))) * 512,
    )


def _record_regular(
    records: dict[tuple[int, int], tuple[int, int]], info: os.stat_result
) -> tuple[int, int]:
    """Record one inode using per-dimension maxima and return its key."""

    key = (int(info.st_dev), int(info.st_ino))
    logical, allocated = _size_pair(info)
    old_logical, old_allocated = records.get(key, (0, 0))
    records[key] = (
        max(old_logical, logical),
        max(old_allocated, allocated),
    )
    return key


def _read_real_uid(status_path: str) -> int | None:
    try:
        with open(status_path, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("Uid:"):
                    fields = line.split()
                    return int(fields[1]) if len(fields) >= 2 else None
    except (OSError, ValueError):
        return None
    return None


def _numeric_pid_names(proc_root: str) -> list[str]:
    with os.scandir(proc_root) as iterator:
        return [entry.name for entry in iterator if entry.name.isdigit()]


def bounded_task_storage_usage(
    root: str,
    entry_limit: int,
    uid: int,
    fd_entry_limit: int,
    *,
    proc_root: str = "/proc",
    pid_names: Iterable[str] | None = None,
) -> dict[str, int | bool]:
    """Measure task-owned storage without following work-tree symlinks.

    Regular files are deduplicated by ``(st_dev, st_ino)`` across hardlinks and
    open descriptors.  If an inode changes while it is observed, the greatest
    logical and allocated sizes seen in this scan are charged once.  Directory,
    symlink, socket, and pipe metadata retain the prior per-entry accounting.

    Vanishing PIDs/FDs are normal procfs races and are skipped.  Failure to list
    the proc root itself is not suppressed: the verifier must not silently run
    without its resource observer.
    """

    if entry_limit < 0 or fd_entry_limit < 0:
        raise ValueError("resource-accounting entry limits must be nonnegative")

    records: dict[tuple[int, int], tuple[int, int]] = {}
    metadata_logical = 0
    metadata_allocated = 0
    metadata_charged = 0
    entries = 0
    stack = [root]
    entry_limit_exceeded = False

    while stack and not entry_limit_exceeded:
        current = stack.pop()
        try:
            iterator = os.scandir(current)
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            continue
        with iterator:
            for entry in iterator:
                entries += 1
                if entries > entry_limit:
                    entry_limit_exceeded = True
                    break
                try:
                    info = entry.stat(follow_symlinks=False)
                except (FileNotFoundError, PermissionError):
                    continue
                if stat.S_ISREG(info.st_mode):
                    _record_regular(records, info)
                else:
                    logical, allocated = _size_pair(info)
                    metadata_logical += logical
                    metadata_allocated += allocated
                    metadata_charged += max(logical, allocated)
                    if stat.S_ISDIR(info.st_mode):
                        stack.append(entry.path)

    # The caller rejects an over-limit work tree immediately.  Avoid doing more
    # attacker-influenced scanning once that decisive bounded result is known.
    if entry_limit_exceeded:
        return _finish_usage(
            records,
            metadata_logical,
            metadata_allocated,
            metadata_charged,
            entries=entries,
            entry_limit_exceeded=True,
        )

    pids = (
        [str(pid) for pid in pid_names]
        if pid_names is not None
        else _numeric_pid_names(proc_root)
    )
    open_fd_entries = 0
    open_regular_keys: set[tuple[int, int]] = set()
    proc_race_skips = 0
    fd_entry_limit_exceeded = False

    for pid in pids:
        if not pid.isdigit():
            continue
        process_dir = os.path.join(proc_root, pid)
        status_path = os.path.join(process_dir, "status")
        if _read_real_uid(status_path) != uid:
            continue

        process_records: dict[tuple[int, int], tuple[int, int]] = {}
        process_open_keys: set[tuple[int, int]] = set()
        try:
            iterator = os.scandir(os.path.join(process_dir, "fd"))
        except OSError as exc:
            if _is_proc_race(exc) or isinstance(exc, PermissionError):
                proc_race_skips += 1
                continue
            raise
        with iterator:
            for fd_entry in iterator:
                open_fd_entries += 1
                if open_fd_entries > fd_entry_limit:
                    fd_entry_limit_exceeded = True
                    break
                try:
                    info = os.stat(fd_entry.path)
                except OSError as exc:
                    if _is_proc_race(exc) or isinstance(exc, PermissionError):
                        proc_race_skips += 1
                        continue
                    raise
                if stat.S_ISREG(info.st_mode):
                    key = _record_regular(process_records, info)
                    process_open_keys.add(key)
        if fd_entry_limit_exceeded:
            break

        # Do not attribute descriptors across a PID-reuse/credential race.  The
        # process-local records are merged only if ownership is stable.
        if _read_real_uid(status_path) != uid:
            proc_race_skips += 1
            continue
        open_regular_keys.update(process_open_keys)
        for key, (logical, allocated) in process_records.items():
            old_logical, old_allocated = records.get(key, (0, 0))
            records[key] = (
                max(old_logical, logical),
                max(old_allocated, allocated),
            )

    return _finish_usage(
        records,
        metadata_logical,
        metadata_allocated,
        metadata_charged,
        entries=entries,
        entry_limit_exceeded=False,
        open_fd_entries=open_fd_entries,
        open_regular_inodes=len(open_regular_keys),
        proc_race_skips=proc_race_skips,
        fd_entry_limit_exceeded=fd_entry_limit_exceeded,
    )


def _finish_usage(
    records: dict[tuple[int, int], tuple[int, int]],
    metadata_logical: int,
    metadata_allocated: int,
    metadata_charged: int,
    *,
    entries: int,
    entry_limit_exceeded: bool,
    open_fd_entries: int = 0,
    open_regular_inodes: int = 0,
    proc_race_skips: int = 0,
    fd_entry_limit_exceeded: bool = False,
) -> dict[str, int | bool]:
    return {
        "logical_bytes": metadata_logical + sum(pair[0] for pair in records.values()),
        "allocated_bytes": metadata_allocated + sum(pair[1] for pair in records.values()),
        # Charge each deduplicated inode once at the greater of its logical or
        # allocated size.  Taking max only after globally summing the two
        # dimensions would undercount a mix of sparse and preallocated files.
        "charged_bytes": metadata_charged
        + sum(max(pair) for pair in records.values()),
        "entries": entries,
        "regular_inodes": len(records),
        "open_fd_entries": open_fd_entries,
        "open_regular_inodes": open_regular_inodes,
        "proc_race_skips": proc_race_skips,
        "entry_limit_exceeded": entry_limit_exceeded,
        "fd_entry_limit_exceeded": fd_entry_limit_exceeded,
    }
