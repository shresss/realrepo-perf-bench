from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from resource_accounting import _finish_usage, bounded_task_storage_usage


def _fake_process(proc_root: Path, pid: int, uid: int) -> Path:
    process = proc_root / str(pid)
    (process / "fd").mkdir(parents=True)
    (process / "status").write_text(
        f"Name:\ttest\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n",
        encoding="utf-8",
    )
    return process


def test_deduplicates_hardlinks_and_open_fds_using_per_inode_maxima(
    tmp_path: Path, monkeypatch
):
    work = tmp_path / "work"
    work.mkdir()
    payload = work / "payload"
    payload.write_bytes(b"x" * 4096)
    os.link(payload, work / "hardlink")

    proc_root = tmp_path / "proc"
    process = _fake_process(proc_root, 101, 1234)
    (process / "fd" / "3").symlink_to(payload)
    (process / "fd" / "4").symlink_to(payload)

    real = payload.stat()
    original_stat = os.stat

    def growing_stat(path, *args, **kwargs):
        if str(path).startswith(str(process / "fd")):
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600,
                st_dev=real.st_dev,
                st_ino=real.st_ino,
                st_size=8192,
                st_blocks=max(real.st_blocks, 24),
            )
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", growing_stat)
    usage = bounded_task_storage_usage(
        str(work), 10, 1234, 10, proc_root=str(proc_root)
    )

    assert usage["entries"] == 2
    assert usage["regular_inodes"] == 1
    assert usage["open_regular_inodes"] == 1
    assert usage["logical_bytes"] == 8192
    assert usage["allocated_bytes"] == max(real.st_blocks, 24) * 512
    assert usage["charged_bytes"] == max(
        8192, max(real.st_blocks, 24) * 512
    )


def test_charges_each_inode_at_max_logical_or_allocated_size_once():
    usage = _finish_usage(
        {(1, 1): (100, 0), (1, 2): (0, 100)},
        0,
        0,
        0,
        entries=2,
        entry_limit_exceeded=False,
    )

    assert usage["logical_bytes"] == 100
    assert usage["allocated_bytes"] == 100
    assert usage["charged_bytes"] == 200


def test_counts_deleted_file_held_open_by_target_process(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    proc_root = tmp_path / "proc"
    process = _fake_process(proc_root, 101, os.getuid())
    before = bounded_task_storage_usage(
        str(work), 10, os.getuid(), 4096, proc_root=str(proc_root)
    )

    deleted = tmp_path / "held-then-deleted"
    deleted.write_bytes(b"z" * (1024 * 1024))
    descriptor = os.open(deleted, os.O_RDONLY)
    try:
        deleted.unlink()
        # /dev/fd keeps referring to the open inode after its last directory
        # entry is removed.  Point the fake proc descriptor at that live FD so
        # this remains a real deleted-open-file test on Linux and macOS.
        (process / "fd" / "3").symlink_to(f"/dev/fd/{descriptor}")
        after = bounded_task_storage_usage(
            str(work), 10, os.getuid(), 4096, proc_root=str(proc_root)
        )
    finally:
        os.close(descriptor)

    assert after["logical_bytes"] >= before["logical_bytes"] + 1024 * 1024
    assert after["open_regular_inodes"] >= before["open_regular_inodes"] + 1


@pytest.mark.skipif(
    not Path("/proc/self/status").exists(), reason="requires Linux procfs"
)
def test_real_linux_proc_counts_deleted_open_file(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    pid = str(os.getpid())
    before = bounded_task_storage_usage(
        str(work), 10, os.getuid(), 4096, pid_names=[pid]
    )

    deleted = tmp_path / "linux-deleted-open"
    deleted.write_bytes(b"z" * (1024 * 1024))
    descriptor = os.open(deleted, os.O_RDONLY)
    try:
        deleted.unlink()
        after = bounded_task_storage_usage(
            str(work), 10, os.getuid(), 4096, pid_names=[pid]
        )
    finally:
        os.close(descriptor)

    assert after["logical_bytes"] >= before["logical_bytes"] + 1024 * 1024
    assert after["open_regular_inodes"] >= before["open_regular_inodes"] + 1


def test_excludes_open_files_from_other_uids(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    target_file = tmp_path / "target"
    other_file = tmp_path / "other"
    target_file.write_bytes(b"t" * 111)
    other_file.write_bytes(b"o" * 777)

    proc_root = tmp_path / "proc"
    target = _fake_process(proc_root, 101, 1234)
    other = _fake_process(proc_root, 202, 9999)
    (target / "fd" / "3").symlink_to(target_file)
    (other / "fd" / "3").symlink_to(other_file)

    usage = bounded_task_storage_usage(
        str(work), 10, 1234, 10, proc_root=str(proc_root)
    )

    assert usage["logical_bytes"] == 111
    assert usage["open_regular_inodes"] == 1


def test_tolerates_vanished_proc_fd(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    proc_root = tmp_path / "proc"
    process = _fake_process(proc_root, 101, 1234)
    (process / "fd" / "3").symlink_to(tmp_path / "already-gone")

    usage = bounded_task_storage_usage(
        str(work), 10, 1234, 10, proc_root=str(proc_root), pid_names=["101", "404"]
    )

    assert usage["logical_bytes"] == 0
    assert usage["proc_race_skips"] == 1


def test_directory_entry_limit_stops_before_proc_scan(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    for name in ("one", "two", "three"):
        (work / name).write_bytes(b"x")

    usage = bounded_task_storage_usage(
        str(work), 2, 1234, 10, proc_root=str(tmp_path / "missing-proc")
    )

    assert usage["entry_limit_exceeded"] is True
    assert usage["entries"] == 3
    assert usage["open_fd_entries"] == 0


def test_open_fd_entry_limit_is_reported(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    external = tmp_path / "external"
    external.write_bytes(b"payload")
    proc_root = tmp_path / "proc"
    process = _fake_process(proc_root, 101, 1234)
    (process / "fd" / "3").symlink_to(external)
    (process / "fd" / "4").symlink_to(external)

    usage = bounded_task_storage_usage(
        str(work), 10, 1234, 1, proc_root=str(proc_root)
    )

    assert usage["fd_entry_limit_exceeded"] is True
    assert usage["open_fd_entries"] == 2
