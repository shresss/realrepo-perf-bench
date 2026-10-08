#!/usr/bin/env python3
"""Best-effort root epilogue: kill task-role processes before publication."""

from __future__ import annotations

import os
import signal
import sys
import time


TARGET_UIDS = {int(value) for value in sys.argv[1:]}
SELF = os.getpid()


def matching_pids() -> list[int]:
    matches = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        if pid in {1, SELF, os.getppid()}:
            continue
        try:
            with open(f"/proc/{pid}/status", encoding="utf-8") as handle:
                uid_line = next(line for line in handle if line.startswith("Uid:"))
            real_uid = int(uid_line.split()[1])
        except (FileNotFoundError, PermissionError, StopIteration, ValueError):
            continue
        if real_uid in TARGET_UIDS:
            matches.append(pid)
    return matches


deadline = time.monotonic() + 3.0
while True:
    pids = matching_pids()
    if not pids:
        raise SystemExit(0)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if time.monotonic() >= deadline:
        print(f"non-quiescent task-role processes: {matching_pids()}", file=sys.stderr)
        raise SystemExit(1)
    time.sleep(0.05)
