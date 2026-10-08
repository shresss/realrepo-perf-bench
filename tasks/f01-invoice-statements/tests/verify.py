"""Verifier for f01-invoice-statements (hardened 2026-09-30, template for every task).

Writes, in this order and from this process only: metrics.json (every number and every
reason), reward.txt (1 or 0), reward.json ({"reward": 0|1}, numbers only). test.sh has
already emptied /logs/verifier, so nothing an agent planted survives.

Gates, in order (the first failure names `reason`):
  1. tamper          fixtures under /app/workloads restored from pristine copies; hashes recorded.
  2. diagnostics     pytest runs under a constrained child, but is diagnostic because submitted
                     Python shares that interpreter. Reward correctness comes from root-owned,
                     type-strict black-box local-path and service-path output oracles.
  3. hidden_workload job output on unseen databases (different seed, month, scale, skew; three seeds
                     at the large size so a cache keyed on content cannot help) must equal an
                     independent oracle by parsed JSON structure and values.
  4. trusted_meter   the hidden database is opened only by a verifier-owned service running under a
                     different UID.  It records every request plus rows/bytes returned on a parent-only
                     channel; submitted code cannot rewrite those observations.
  5. perf_bar        database requests must be <= baseline/50 on EVERY hidden database (the count must
                     stop growing with input size). The baseline uses the same service boundary.
  6. wallclock       a conservative regression guard from an EXTERNAL clock: median paired large-case
                     agent/baseline ratio <= 1.25. Cross-size timing is diagnostic, not a speed claim.
  7. history_work    paired databases have identical target-month output, while the history twin adds
                     100 old invoices/customer x four lines. Absolute and paired delivered-row,
                     response-byte, and server-owned SQLite VM-work bounds must hold. CPU/wall ratios
                     are diagnostic only.
Graded score (metrics only): log-ratio improvement vs the reference (3 statements), floored at 0.25
of the reference improvement.
"""
import atexit
import ctypes
import hashlib
import json
import math
import os
import random
import resource
import secrets
import signal
import shutil
import sqlite3
import stat
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

VERIFIER_STARTED_MONOTONIC = time.monotonic()

# Container layout is fixed. `--local-root DIR` (used only by our QC scripts, never by
# Harbor, which invokes test.sh with no arguments) points at DIR/app, DIR/tests, DIR/logs.
_ROOT = sys.argv[sys.argv.index("--local-root") + 1] if "--local-root" in sys.argv else ""
TESTS = os.path.join(_ROOT, "tests") if _ROOT else "/tests"
APP = os.path.join(_ROOT, "app") if _ROOT else "/app"
PUBLISH_LOGS = os.path.join(_ROOT, "logs", "verifier") if _ROOT else "/logs/verifier"
# Docker Desktop bind mounts can ignore Linux DAC for container UIDs. Never keep
# live verifier evidence on Harbor's host-mounted publication path while submitted
# code is running. Official runs stage everything in the root-only image layer;
# test.sh quiesces candidate identities, scrubs the mount, and publishes afterward.
LOGS = PUBLISH_LOGS if _ROOT else "/tests/.runtime-verifier"
PRISTINE_SRC = os.path.join(TESTS, "pristine_src")      # unmodified package = baseline
PRISTINE_WORKLOADS = os.path.join(TESTS, "pristine")    # gen_data.py, run_visible.sh
SUITE = os.path.join(TESTS, "test_statements.py")
# Official hidden values come from a coordinator-supplied block seed or an exact
# root-only replay manifest.  Local compatibility runs may use OS entropy.  Derived
# cases are recorded after the task for same-artifact regrade; submitted children
# never receive the seed, block id, or manifest.
_HIDDEN_LAYOUT = {"n": (1000, 1), "8n": (8000, 3)}
_HIDDEN_MONTHS = ("2025-12", "2026-02", "2026-03", "2027-01")
_SHAPE = ["--zero-frac", "0.30", "--min-inv", "1", "--max-inv", "6",
          "--tail-frac", "0.01", "--tail-min", "200", "--tail-max", "1500", "--missing-product-frac", "0.06"]
BAR_DIVISOR = 50          # agent statements must be <= baseline / 50 on every hidden database
Q_REF = 3                 # the reference solution's statement count (independent of size):
                          # customers, the month's invoices, the month's lines joined to products
SCORE_FLOOR = 0.25        # graded score is 0 below this fraction of the reference improvement
WALLCLOCK_RATIO = 1.25    # conservative large-case sanity ceiling, not a speedup estimator
RUN_TIMEOUT = {"n": 60, "8n": 120}
CANDIDATE_TOTAL_WALL_SECONDS = 240
HISTORY_CUSTOMERS = 1000
HISTORY_INVOICES_PER_CUSTOMER = 100
HISTORY_LINES_PER_INVOICE = 4
HISTORY_ATTEMPTS = 3
HISTORY_ROW_ABSOLUTE_ALLOWANCE = 2000
HISTORY_ROW_RELATIVE_ALLOWANCE = 0.05
HISTORY_RESPONSE_BYTE_ABSOLUTE_ALLOWANCE = 2 * 1024 * 1024
HISTORY_RESPONSE_BYTE_RELATIVE_ALLOWANCE = 0.05
HISTORY_VM_STEP_ABSOLUTE_ALLOWANCE = 1_000_000
HISTORY_VM_STEP_RELATIVE_ALLOWANCE = 0.25
TASK_CPU_SECONDS = 610
TASK_ADDRESS_SPACE_BYTES = 512 * 1024 * 1024
TASK_FILE_BYTES = 96 * 1024 * 1024
TASK_JOBDIR_BYTES = 256 * 1024 * 1024
TASK_JOBDIR_ENTRIES = 10_000
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
TASK_OPEN_FILES = 256
TASK_PROCESSES = 4
TASK_FD_SCAN_ENTRIES = TASK_OPEN_FILES * TASK_PROCESSES
SHARED_SCRATCH_PATHS = (
    "/tmp",
    "/var/tmp",
    "/dev/shm",
    "/dev/mqueue",
    "/run/lock",
)
TASK_UID = 10001
TASK_GID = 10001
METER_UID = 10002
METER_GID = 10002
BASELINE_UID = 10003
BASELINE_GID = 10003
MAX_CHILD_OUTPUT_BYTES = 4 * 1024 * 1024
CHILD_OUTPUT_TAIL_BYTES = 64 * 1024
RC_TIMEOUT = -90
RC_OUTPUT_LIMIT = -91
RC_ISOLATION = -92
RC_VERIFIER_BUDGET = -93
RC_RESOURCE_LIMIT = -94
VERIFIER_TIMEOUT_SECONDS = 900
VERIFIER_EPILOGUE_RESERVE_SECONDS = 60
VERIFIER_WORK_DEADLINE = (
    VERIFIER_STARTED_MONOTONIC
    + VERIFIER_TIMEOUT_SECONDS
    - VERIFIER_EPILOGUE_RESERVE_SECONDS
)
PRIVILEGE_ISOLATION = os.geteuid() == 0
LOCAL_COMPATIBILITY = bool(_ROOT)


def _make_hidden_workloads():
    supplied = (os.environ.get("F01_EVAL_SEED") or "").strip()
    block_id = (os.environ.get("F01_EVAL_BLOCK_ID") or "").strip()
    replay_raw = (os.environ.get("F01_REPLAY_MANIFEST_JSON") or "").strip()
    configuration_error = None

    if replay_raw:
        try:
            replay = json.loads(replay_raw)
            if not isinstance(replay, dict) or set(replay) != {
                "workloads", "history", "sentinel_seed"
            }:
                raise ValueError("replay manifest keys are invalid")
            workloads = replay["workloads"]
            if not isinstance(workloads, dict) or set(workloads) != set(_HIDDEN_LAYOUT):
                raise ValueError("replay workload tags are invalid")
            for tag, (customers, count) in _HIDDEN_LAYOUT.items():
                entry = workloads[tag]
                if (
                    not isinstance(entry, dict)
                    or entry.get("customers") != customers
                    or not isinstance(entry.get("cases"), list)
                    or len(entry["cases"]) != count
                ):
                    raise ValueError(f"replay workload shape is invalid for {tag}")
                for case in entry["cases"]:
                    if (
                        not isinstance(case, dict)
                        or set(case) != {"seed", "month"}
                        or type(case["seed"]) is not int
                        or case["seed"] < 1
                        or case["month"] not in _HIDDEN_MONTHS
                    ):
                        raise ValueError(f"replay case is invalid for {tag}")
            history = replay["history"]
            if (
                not isinstance(history, dict)
                or set(history) != {"seed", "month"}
                or type(history["seed"]) is not int
                or history["seed"] < 1
                or history["month"] not in _HIDDEN_MONTHS
            ):
                raise ValueError("replay history case is invalid")
            sentinel_seed = replay["sentinel_seed"]
            if type(sentinel_seed) is not int or sentinel_seed < 1:
                raise ValueError("replay sentinel seed is invalid")
            if not LOCAL_COMPATIBILITY and not block_id:
                configuration_error = "official replay requires F01_EVAL_BLOCK_ID"
            provenance = {
                "source": "exact_replay_manifest",
                "block_id": block_id or None,
                "manifest_sha256": hashlib.sha256(replay_raw.encode("utf-8")).hexdigest(),
                "workloads": workloads,
                "history": history,
                "sentinel_seed": sentinel_seed,
                "replay_manifest": replay,
            }
            return workloads, history, sentinel_seed, provenance, configuration_error
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            configuration_error = f"invalid F01_REPLAY_MANIFEST_JSON: {exc}"

    if not LOCAL_COMPATIBILITY and (not supplied or not block_id):
        configuration_error = (
            configuration_error
            or "official evaluation requires F01_EVAL_SEED and F01_EVAL_BLOCK_ID"
        )
    master = supplied or secrets.token_hex(32)
    seed_material = hashlib.sha256(master.encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(seed_material, "big"))
    months = list(_HIDDEN_MONTHS)
    rng.shuffle(months)
    workloads = {}
    month_index = 0
    for tag, (customers, count) in _HIDDEN_LAYOUT.items():
        cases = []
        for _ in range(count):
            cases.append({
                "seed": rng.randrange(1_000_000, 2_147_000_000),
                "month": months[month_index % len(months)],
            })
            month_index += 1
        workloads[tag] = {"customers": customers, "cases": cases}
    history = {
        "seed": rng.randrange(1_000_000, 2_147_000_000),
        "month": months[month_index % len(months)],
    }
    sentinel_seed = rng.randrange(1_000_000, 2_147_000_000)
    provenance = {
        "source": "coordinator_seed" if supplied else "local_os_entropy",
        "block_id": block_id or None,
        "master_commitment_sha256": hashlib.sha256(master.encode("utf-8")).hexdigest(),
        "workloads": workloads,
        "history": history,
        "sentinel_seed": sentinel_seed,
        "replay_manifest": {
            "workloads": workloads,
            "history": history,
            "sentinel_seed": sentinel_seed,
        },
    }
    return workloads, history, sentinel_seed, provenance, configuration_error


(
    HIDDEN,
    HISTORY_CASE,
    SENTINEL_SEED,
    WORKLOAD_PROVENANCE,
    SEED_CONFIGURATION_ERROR,
) = _make_hidden_workloads()
candidate_wall_seconds = 0.0
candidate_execution_started = False

metrics = {"task": "f01-invoice-statements", "verifier_version": "4.2.2-private-evidence", "reason": None,
           "checks": {}, "hidden": {}, "notes": [],
           "workload_provenance": WORKLOAD_PROVENANCE}
sys.path.insert(0, TESTS)
import oracle  # noqa: E402
from causal_validity import classify_causal_validity  # noqa: E402
from exact_json import first_json_difference, load_exact_json  # noqa: E402
from resource_accounting import bounded_task_storage_usage  # noqa: E402
from selectivity_work import relevant_work_profile, selective_work_ceilings  # noqa: E402
from trusted_sqlite_service import MeteredSQLiteService  # noqa: E402


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def finish(reward: int, reason, *, validity_override=None):
    """metrics.json first, reward.txt second, reward.json LAST (Harbor prefers reward.json)."""
    metrics["reason"] = reason
    metrics["reward"] = reward
    causal_validity = classify_causal_validity(
        reason,
        candidate_execution_started=candidate_execution_started,
        override=validity_override,
    )
    metrics["causal_validity"] = causal_validity
    if LOCAL_COMPATIBILITY:
        metrics["validity"] = "local_untrusted_diagnostic"
        metrics["execution_trust"] = (
            "untrusted: --local-root compatibility run; never approval evidence"
        )
    elif not PRIVILEGE_ISOLATION:
        metrics["validity"] = causal_validity
        metrics["execution_trust"] = "official verifier isolation unavailable"
    else:
        metrics["validity"] = causal_validity
        metrics["execution_trust"] = "official separate verifier with UID isolation"
    # Harbor requires a numeric reward artifact even when the evaluator itself is
    # invalid.  Keep that transport value explicit and make the analytical value
    # nullable so downstream statistics cannot silently treat infrastructure loss
    # as a model failure.  Only score_eligible trials belong in the primary
    # capability denominator; invalid trials require same-artifact regrade.
    metrics["score_eligible"] = metrics["validity"] == "valid_model_outcome"
    metrics["model_reward"] = reward if metrics["score_eligible"] else None
    metrics["transport_reward"] = reward
    metrics["denominator_policy"] = (
        "include model_reward in primary estimate"
        if metrics["score_eligible"]
        else "exclude from primary estimate and regrade the same artifact"
    )
    metrics["verifier_budget"] = {
        "configured_timeout_seconds": VERIFIER_TIMEOUT_SECONDS,
        "epilogue_reserve_seconds": VERIFIER_EPILOGUE_RESERVE_SECONDS,
        "elapsed_seconds": round(time.monotonic() - VERIFIER_STARTED_MONOTONIC, 4),
        "work_seconds_remaining": round(
            max(0.0, VERIFIER_WORK_DEADLINE - time.monotonic()), 4
        ),
    }
    os.makedirs(LOGS, exist_ok=True)
    with open(os.path.join(LOGS, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(LOGS, "reward.txt"), "w") as fh:
        fh.write(f"{reward}\n")
    with open(os.path.join(LOGS, "reward.json"), "w") as fh:
        json.dump({"reward": reward}, fh)
    print(f"reward={reward} reason={reason}")
    sys.exit(0)


def require_verifier_budget(stage: str, minimum_seconds: float = 5.0) -> None:
    """Fail invalid before Harbor's hard timeout can erase typed evidence."""

    remaining = VERIFIER_WORK_DEADLINE - time.monotonic()
    if remaining < minimum_seconds:
        metrics["notes"].append(
            f"verifier budget exhausted before {stage}: {remaining:.3f}s remain"
        )
        finish(0, "verifier_budget_exhausted")


def clean_env(app=APP, home="/tmp"):
    """Build a fixed child environment: no parent credentials, Python hooks, or pytest controls."""
    return {
        "HOME": home,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "LEDGERLY_APP": app,
        "TMPDIR": home,
    }


def _drop_to_user(uid, gid):
    """Child-only hook. The verifier stays root; the child permanently drops identity."""
    # Linux PR_SET_NO_NEW_PRIVS: a task cannot regain privilege through any setuid
    # binary or file capability present in the base image after we drop UID/GID.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_NO_NEW_PRIVS) failed")
    os.umask(0o077)
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (TASK_CPU_SECONDS, TASK_CPU_SECONDS))
    resource.setrlimit(
        resource.RLIMIT_AS,
        (TASK_ADDRESS_SPACE_BYTES, TASK_ADDRESS_SPACE_BYTES),
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (TASK_FILE_BYTES, TASK_FILE_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (TASK_OPEN_FILES, TASK_OPEN_FILES))
    resource.setrlimit(resource.RLIMIT_NPROC, (TASK_PROCESSES, TASK_PROCESSES))
    if hasattr(resource, "RLIMIT_MSGQUEUE"):
        resource.setrlimit(resource.RLIMIT_MSGQUEUE, (0, 0))


def _processes_for_uid(uid):
    found = []
    if not PRIVILEGE_ISOLATION:
        return found
    own_pid = os.getpid()
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit() or int(entry.name) == own_pid:
            continue
        try:
            with open(os.path.join(entry.path, "status"), encoding="utf-8") as fh:
                uid_line = next(line for line in fh if line.startswith("Uid:"))
            if int(uid_line.split()[1]) == uid:
                found.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError, StopIteration, ValueError):
            pass
    return found


def _kill_lingering_processes(uid):
    """Kill a dedicated run identity and prove that no same-UID process survived."""
    if not PRIVILEGE_ISOLATION:
        return []
    remaining = []
    for _ in range(20):
        remaining = _processes_for_uid(uid)
        if not remaining:
            return []
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(0.01)
    return _processes_for_uid(uid)


def _list_sysv_ipc_for_uid(uid):
    objects = []
    errors = []
    for kind, identifier_name in (
        ("shm", "shmid"),
        ("msg", "msqid"),
        ("sem", "semid"),
    ):
        path = f"/proc/sysvipc/{kind}"
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError as exc:
            errors.append(f"{kind}:unreadable:{type(exc).__name__}")
            continue
        if not lines:
            continue
        columns = lines[0].split()
        try:
            id_index = columns.index(identifier_name)
            uid_index = columns.index("uid")
        except ValueError:
            errors.append(f"{kind}:unexpected_header")
            continue
        for line in lines[1:]:
            fields = line.split()
            if len(fields) <= max(id_index, uid_index):
                errors.append(f"{kind}:malformed_row")
                continue
            try:
                identifier = int(fields[id_index])
                owner_uid = int(fields[uid_index])
            except ValueError:
                errors.append(f"{kind}:noninteger_row")
                continue
            if owner_uid != uid:
                continue
            objects.append({"kind": kind, "id": identifier})
    return objects, errors


def _remove_sysv_ipc_for_uid(uid):
    """Remove persistent IPC as its owner, then prove the namespace is empty."""

    if not PRIVILEGE_ISOLATION:
        return [], []
    objects, errors = _list_sysv_ipc_for_uid(uid)
    if not objects or errors:
        return [], errors
    pid = os.fork()
    if pid == 0:
        try:
            os.setgroups([])
            os.setgid(uid)
            os.setuid(uid)
            libc = ctypes.CDLL(None, use_errno=True)
            failed = False
            for item in objects:
                if item["kind"] == "shm":
                    rc = libc.shmctl(item["id"], 0, None)
                elif item["kind"] == "msg":
                    rc = libc.msgctl(item["id"], 0, None)
                else:
                    rc = libc.semctl(item["id"], 0, 0)
                failed = failed or rc != 0
            os._exit(1 if failed else 0)
        except BaseException:
            os._exit(2)
    _, status = os.waitpid(pid, 0)
    remaining, rescan_errors = _list_sysv_ipc_for_uid(uid)
    remaining_keys = {(item["kind"], item["id"]) for item in remaining}
    removed = [
        item
        for item in objects
        if (item["kind"], item["id"]) not in remaining_keys
    ]
    errors.extend(rescan_errors)
    if status != 0:
        errors.append(f"cleanup_child_status={status}")
    errors.extend(
        f"{item['kind']}:{item['id']}:still_present" for item in remaining
    )
    return removed, errors


class ChildLaunchError(RuntimeError):
    pass


class VerifierBudgetExhausted(RuntimeError):
    pass


def run(cmd, timeout, cwd=APP, *, unprivileged=False, app=APP, home=None,
        child_uid=TASK_UID, child_gid=TASK_GID):
    """Run a child with bounded output and externally owned clocks/cleanup.

    The final boolean says whether ``Popen`` succeeded.  Callers use it to avoid
    treating a pre-receipt verifier-budget failure as candidate action.
    """
    if unprivileged and not os.path.isdir(cwd):
        raise RuntimeError(f"isolated cwd does not exist: {cwd}")
    verifier_seconds_remaining = VERIFIER_WORK_DEADLINE - time.monotonic()
    if verifier_seconds_remaining <= 0:
        return (
            RC_VERIFIER_BUDGET,
            "verifier work deadline exhausted before child launch",
            0.0,
            0.0,
            False,
        )
    deadline_limited = verifier_seconds_remaining < timeout
    effective_timeout = min(timeout, verifier_seconds_remaining)
    child_home = home or cwd
    ru0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.perf_counter()
    proc = None
    reader = None
    output_state = {"tail": bytearray(), "total": 0}
    output_limit = threading.Event()
    timed_out = False
    resource_limit_reason = None
    resource_usage = None
    cleanup_survivors = []
    cleanup_ipc = []
    cleanup_ipc_errors = []

    def drain_output():
        stream = proc.stdout
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                output_state["total"] += len(chunk)
                tail = output_state["tail"]
                tail.extend(chunk)
                if len(tail) > CHILD_OUTPUT_TAIL_BYTES:
                    del tail[:-CHILD_OUTPUT_TAIL_BYTES]
                if output_state["total"] > MAX_CHILD_OUTPUT_BYTES:
                    output_limit.set()
        finally:
            try:
                stream.close()
            except OSError:
                pass

    if unprivileged:
        preexisting = _kill_lingering_processes(child_uid)
        preexisting_ipc, preexisting_ipc_errors = _remove_sysv_ipc_for_uid(
            child_uid
        )
        if preexisting or preexisting_ipc or preexisting_ipc_errors:
            raise ChildLaunchError(
                f"dedicated UID {child_uid} was not empty before launch: "
                f"processes={preexisting[:8]} ipc={preexisting_ipc[:8]} "
                f"ipc_errors={preexisting_ipc_errors[:8]}"
            )
    try:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                env=clean_env(app=app, home=child_home),
                start_new_session=unprivileged,
                preexec_fn=(lambda: _drop_to_user(child_uid, child_gid))
                if unprivileged and PRIVILEGE_ISOLATION else None,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ChildLaunchError(f"child launch failed: {type(exc).__name__}: {exc}") from exc
        reader = threading.Thread(target=drain_output, name="bounded-child-output", daemon=True)
        reader.start()
        deadline = time.monotonic() + effective_timeout
        next_resource_check = time.monotonic()
        while proc.poll() is None:
            now = time.monotonic()
            if unprivileged and now >= next_resource_check:
                resource_usage = bounded_task_storage_usage(
                    cwd,
                    TASK_JOBDIR_ENTRIES,
                    child_uid,
                    TASK_FD_SCAN_ENTRIES,
                )
                if resource_usage["entry_limit_exceeded"]:
                    resource_limit_reason = (
                        f"job directory exceeded {TASK_JOBDIR_ENTRIES} entries"
                    )
                elif resource_usage["fd_entry_limit_exceeded"]:
                    resource_limit_reason = (
                        f"task processes exceeded {TASK_FD_SCAN_ENTRIES} open-file entries"
                    )
                elif resource_usage["charged_bytes"] > TASK_JOBDIR_BYTES:
                    resource_limit_reason = (
                        f"task storage exceeded {TASK_JOBDIR_BYTES} bytes"
                    )
                next_resource_check = now + 0.05
            if output_limit.is_set() or resource_limit_reason is not None or now >= deadline:
                timed_out = (
                    not output_limit.is_set() and resource_limit_reason is None
                )
                if unprivileged:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                break
            time.sleep(0.01)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        rc = proc.returncode if proc.returncode is not None else -9
    finally:
        if unprivileged and proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            cleanup_survivors = _kill_lingering_processes(child_uid)
            cleanup_ipc, cleanup_ipc_errors = _remove_sysv_ipc_for_uid(
                child_uid
            )
        if reader is not None:
            reader.join(timeout=5)
            if reader.is_alive() and proc is not None and proc.stdout is not None:
                try:
                    proc.stdout.close()
                except OSError:
                    pass
                reader.join(timeout=1)
    wall = time.perf_counter() - t0
    ru1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (ru1.ru_utime + ru1.ru_stime) - (ru0.ru_utime + ru0.ru_stime)
    output = bytes(output_state["tail"]).decode("utf-8", errors="replace")
    if output_limit.is_set():
        rc = RC_OUTPUT_LIMIT
        output += f"\nchild output exceeded {MAX_CHILD_OUTPUT_BYTES} bytes"
    elif resource_limit_reason is not None:
        rc = RC_RESOURCE_LIMIT
        output += f"\n{resource_limit_reason}; observed={resource_usage}"
    elif timed_out:
        if deadline_limited:
            rc = RC_VERIFIER_BUDGET
            output += "\nverifier work deadline exhausted"
        else:
            rc = RC_TIMEOUT
            output += f"\ntimeout after {effective_timeout}s"
    if cleanup_survivors:
        rc = RC_ISOLATION
        output += f"\ndedicated UID {child_uid} retained processes: {cleanup_survivors[:8]}"
    if cleanup_ipc or cleanup_ipc_errors:
        rc = RC_ISOLATION
        output += (
            f"\ndedicated UID {child_uid} retained System V IPC: "
            f"objects={cleanup_ipc[:8]} errors={cleanup_ipc_errors[:8]}"
        )
    return rc, output[-4000:], wall, cpu, proc is not None


def _prepare_private_workdir():
    parent = tempfile.mkdtemp(prefix="f01-verifier-")
    os.chmod(parent, 0o711 if PRIVILEGE_ISOLATION else 0o700)
    return parent


def _lock_shared_scratch():
    """Prevent task children from using shared scratch to communicate across isolated runs."""
    modes = {}
    if not PRIVILEGE_ISOLATION:
        return modes
    for path in SHARED_SCRATCH_PATHS:
        if os.path.isdir(path):
            os.chown(path, 0, 0)
            os.chmod(path, 0o711)
            modes[path] = oct(stat.S_IMODE(os.stat(path).st_mode))
    return modes


def _prepare_child_dir(parent, prefix, uid=TASK_UID, gid=TASK_GID):
    path = tempfile.mkdtemp(prefix=f"{prefix}-", dir=parent)
    os.chmod(path, 0o700)
    if PRIVILEGE_ISOLATION:
        os.chown(path, uid, gid)
    return path


def _prepare_job_root(parent, prefix):
    """Create a root-owned run boundary with no task-writable parent directory."""
    path = tempfile.mkdtemp(prefix=f"{prefix}-", dir=parent)
    if PRIVILEGE_ISOLATION:
        os.chown(path, 0, 0)
        os.chmod(path, 0o711)
    else:
        os.chmod(path, 0o700)
    return path


def _copy_child_readonly(src, dst):
    shutil.copyfile(src, dst)
    if PRIVILEGE_ISOLATION:
        os.chown(dst, 0, 0)
    os.chmod(dst, 0o444)


def _copy_meter_database(src, dst):
    """Install an input database readable only by the verifier's meter identity."""
    shutil.copyfile(src, dst)
    if PRIVILEGE_ISOLATION:
        os.chown(dst, METER_UID, METER_GID)
        os.chmod(dst, 0o400)
    else:
        os.chmod(dst, 0o600)


def _prepare_meter_dir(jobroot):
    """Create a service-owned directory that task code may only traverse."""
    path = os.path.join(jobroot, "meter")
    os.mkdir(path, 0o700)
    if PRIVILEGE_ISOLATION:
        os.chown(path, METER_UID, METER_GID)
        os.chmod(path, 0o711)
    return path


def _prepare_meter_socket_dir():
    """Use a short absolute path: AF_UNIX paths are limited to about 104--108 bytes."""
    path = tempfile.mkdtemp(prefix="f01m-", dir="/tmp")
    if PRIVILEGE_ISOLATION:
        os.chown(path, METER_UID, METER_GID)
        os.chmod(path, 0o711)
    else:
        os.chmod(path, 0o700)
    return path


def _lock_tree_for_child(root):
    """Make a copied trusted source tree readable but immutable to the task UID."""
    for current, dirs, files in os.walk(root, followlinks=False):
        if PRIVILEGE_ISOLATION:
            os.chown(current, 0, 0)
        os.chmod(current, 0o555)
        for name in files:
            path = os.path.join(current, name)
            if os.path.islink(path):
                raise RuntimeError(f"trusted source unexpectedly contains symlink: {path}")
            if PRIVILEGE_ISOLATION:
                os.chown(path, 0, 0)
            os.chmod(path, 0o444)


def _unlock_local_directories(root):
    """Local QC owns both roles, so restore directory write bits before cleanup."""
    if PRIVILEGE_ISOLATION or not os.path.isdir(root):
        return
    for current, dirs, _files in os.walk(root, followlinks=False):
        os.chmod(current, 0o700)


def _validate_and_lock_app():
    """Reject special/out-of-tree entries, then make the restored artifact root-owned/read-only."""
    if not PRIVILEGE_ISOLATION:
        return []
    app_real = os.path.realpath(APP)
    problems = []
    for current, dirs, files in os.walk(APP, topdown=True, followlinks=False):
        for name in dirs + files:
            path = os.path.join(current, name)
            try:
                info = os.lstat(path)
            except OSError as exc:
                problems.append(f"unstatable artifact {path}: {type(exc).__name__}")
                continue
            if stat.S_ISLNK(info.st_mode):
                resolved = os.path.realpath(path)
                try:
                    inside = os.path.commonpath((app_real, resolved)) == app_real
                except ValueError:
                    inside = False
                if not inside or name in dirs:
                    kind = "in-tree directory" if inside else "out-of-tree"
                    problems.append(f"{kind} symlink not allowed in judged artifact: {path}")
                os.lchown(path, 0, 0)
            elif stat.S_ISDIR(info.st_mode):
                os.chown(path, 0, 0)
                os.chmod(path, 0o555)
            elif stat.S_ISREG(info.st_mode):
                executable = bool(info.st_mode & 0o111)
                os.chown(path, 0, 0)
                os.chmod(path, 0o555 if executable else 0o444)
            else:
                problems.append(f"special artifact entry: {path}")
    os.chown(APP, 0, 0)
    os.chmod(APP, 0o555)
    return problems


def _restore_pristine(pristine, destination):
    """Replace an agent artifact without following a symlink or writing through a hard target."""
    if os.path.lexists(destination):
        if os.path.isdir(destination) and not os.path.islink(destination):
            shutil.rmtree(destination)
        else:
            os.unlink(destination)
    temp_path = f"{destination}.restore-{uuid.uuid4().hex}"
    shutil.copyfile(pristine, temp_path)
    if PRIVILEGE_ISOLATION:
        os.chown(temp_path, 0, 0)
    os.chmod(temp_path, 0o444)
    os.replace(temp_path, destination)


def _probe_privilege_boundary(parent):
    """Exercise the exact DAC boundary relied on by adversarial task children."""
    if not PRIVILEGE_ISOLATION:
        return {"enabled": False, "reason": "local verifier is not root; compatibility mode"}
    marker = os.path.join(parent, f"root-marker-{uuid.uuid4().hex}")
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write("verifier-private")
    os.chmod(marker, 0o600)
    probe_dir = _prepare_child_dir(parent, "isolation-probe")
    probe_code = r'''
import json, os, sys
parent, marker, private_logs = sys.argv[1], sys.argv[2], sys.argv[3]
result = {"uid": os.getuid(), "gid": os.getgid()}
def denied(name, action):
    try:
        action()
    except PermissionError:
        result[name] = True
    except Exception as exc:
        result[name] = False
        result[name + "_error"] = type(exc).__name__
    else:
        result[name] = False
denied("tests_read_denied", lambda: open("/tests/oracle.py", "rb").read(1))
denied("tests_write_denied", lambda: open("/tests/task-write-probe", "wb").write(b"x"))
denied("logs_read_denied", lambda: os.listdir(private_logs))
denied("logs_write_denied", lambda: open(os.path.join(private_logs, "task-write-probe"), "wb").write(b"x"))
# Harbor's publication mount is deliberately untrusted during candidate execution.
# Record its host-specific DAC behavior, but never read it as verifier evidence.
denied("publish_logs_read_denied", lambda: os.listdir("/logs/verifier"))
denied("publish_logs_write_denied", lambda: open("/logs/verifier/task-write-probe", "wb").write(b"x"))
denied("app_write_denied", lambda: open("/app/task-write-probe", "wb").write(b"x"))
denied("parent_read_denied", lambda: open(marker, "rb").read(1))
denied("parent_write_denied", lambda: open(os.path.join(parent, "task-write-probe"), "wb").write(b"x"))
denied("signal_parent_denied", lambda: os.kill(os.getppid(), 0))
denied("global_tmp_list_denied", lambda: os.listdir("/tmp"))
denied("global_tmp_write_denied", lambda: open("/tmp/task-write-probe", "wb").write(b"x"))
denied("shared_memory_write_denied", lambda: open("/dev/shm/task-write-probe", "wb").write(b"x"))
denied("message_queue_write_denied", lambda: open("/dev/mqueue/task-write-probe", "wb").write(b"x"))
denied("run_lock_write_denied", lambda: open("/run/lock/task-write-probe", "wb").write(b"x"))
parent_proc = f"/proc/{os.getppid()}"
denied("proc_parent_environ_read_denied", lambda: open(parent_proc + "/environ", "rb").read(1))
denied("proc_parent_mem_read_denied", lambda: open(parent_proc + "/mem", "rb").read(1))
denied("proc_parent_fd_list_denied", lambda: os.listdir(parent_proc + "/fd"))
denied("proc_parent_fd0_readlink_denied", lambda: os.readlink(parent_proc + "/fd/0"))
denied("proc_parent_cwd_readlink_denied", lambda: os.readlink(parent_proc + "/cwd"))
with open("/proc/self/status", encoding="utf-8") as status:
    no_new_privs = next(line for line in status if line.startswith("NoNewPrivs:"))
result["no_new_privs"] = int(no_new_privs.split()[1])
own = os.path.join(os.getcwd(), "own-write-probe")
with open(own, "w", encoding="utf-8") as fh:
    fh.write("ok")
result["dedicated_dir_write_ok"] = os.path.exists(own)
print(json.dumps(result, sort_keys=True))
'''
    try:
        rc, output, _, _, _ = run(
            [sys.executable, "-I", "-c", probe_code, parent, marker, LOGS],
            timeout=30,
            cwd=probe_dir,
            unprivileged=True,
            home=probe_dir,
        )
        try:
            result = json.loads(output.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            result = {"probe_parse_error": f"{type(exc).__name__}: {exc}", "rc": rc, "tail": output[-800:]}
        result["enabled"] = True
        result["rc"] = rc
        return result
    finally:
        for leaked in ("/tests/task-write-probe", os.path.join(LOGS, "task-write-probe"),
                       "/logs/verifier/task-write-probe",
                       "/app/task-write-probe",
                       "/tmp/task-write-probe", "/dev/shm/task-write-probe",
                       "/dev/mqueue/task-write-probe",
                       "/run/lock/task-write-probe",
                       os.path.join(parent, "task-write-probe")):
            try:
                os.unlink(leaked)
            except FileNotFoundError:
                pass
        shutil.rmtree(probe_dir, ignore_errors=True)
        try:
            os.unlink(marker)
        except FileNotFoundError:
            pass


def _read_json_and_unlink(path, label):
    """Parse a job artifact once, then remove it even when it is absent or malformed."""
    value = None
    read_error = None
    cleanup_error = None
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if info.st_size > MAX_OUTPUT_BYTES:
            raise ValueError(
                f"{label} exceeds the {MAX_OUTPUT_BYTES}-byte verifier limit"
            )
        with open(path, encoding="utf-8") as fh:
            value = load_exact_json(fh)
    except Exception as exc:
        read_error = f"{label} unreadable: {type(exc).__name__}: {str(exc)[:180]}"
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            cleanup_error = f"{label} cleanup failed: {type(exc).__name__}: {str(exc)[:180]}"
    return value, read_error, cleanup_error


def _number_or_none(value):
    if type(value) in (int, float):
        try:
            if math.isfinite(value):
                return value
        except (OverflowError, TypeError, ValueError):
            pass
    return None


def run_job(src, source_db, tag, month, parent, role):
    """Run one export through the verifier-owned database service.

    The task process owns only its output file.  Request, row, byte, connection,
    and database-integrity evidence comes from the service over a control pipe
    that is never inherited by submitted code.
    """
    global candidate_wall_seconds, candidate_execution_started
    child_uid, child_gid = (
        (BASELINE_UID, BASELINE_GID) if src == PRISTINE_SRC
        else (TASK_UID, TASK_GID)
    )
    # Candidate-visible paths are intentionally role-neutral; semantic controls,
    # hidden performance cases, and history pairs must not be branchable by cwd.
    jobroot = _prepare_job_root(parent, "run")
    jobdir = _prepare_child_dir(jobroot, "work", child_uid, child_gid)
    fixture_dir = os.path.join(jobroot, "fixture")
    os.mkdir(fixture_dir, 0o700)
    if PRIVILEGE_ISOLATION:
        os.chown(fixture_dir, 0, 0)
    runner = os.path.join(fixture_dir, "run_remote_export.py")
    _copy_child_readonly(os.path.join(TESTS, "run_remote_export.py"), runner)
    child_src = src
    if src != APP:
        child_src = os.path.join(fixture_dir, "trusted-src")
        shutil.copytree(src, child_src)
        _lock_tree_for_child(child_src)
    os.chmod(fixture_dir, 0o555)

    meter_dir = _prepare_meter_dir(jobroot)
    db = os.path.join(meter_dir, "input.db")
    _copy_meter_database(source_db, db)
    socket_dir = _prepare_meter_socket_dir()
    socket_path = os.path.join(socket_dir, "db.sock")
    attempt_id = uuid.uuid4().hex
    db_hash_before = sha256(db)
    out = os.path.join(jobdir, "output.json")
    service = MeteredSQLiteService(
        db,
        socket_path,
        attempt_id,
        db_hash_before,
        drop_privileges=PRIVILEGE_ISOLATION,
        uid=METER_UID,
        gid=METER_GID,
    )
    service_ready = None
    service_report = None
    service_error = None
    runner_launch_error = None
    task_started = False
    rc, child_output, wall, cpu = -1, "task was not started", 0.0, 0.0
    parsed_output = None
    output_error = "output unavailable"
    output_cleanup_error = None
    try:
        service_ready = service.start()
        try:
            requested_timeout = RUN_TIMEOUT[tag]
            if src == APP:
                requested_timeout = min(
                    requested_timeout,
                    max(1.0, CANDIDATE_TOTAL_WALL_SECONDS - candidate_wall_seconds),
                )
            rc, child_output, wall, cpu, child_started = run(
                [sys.executable, "-I", runner, "--src", child_src,
                 "--db", f"metered+unix://{socket_path}",
                 "--month", month, "--out", out],
                timeout=requested_timeout,
                cwd=jobdir,
                unprivileged=True,
                app=child_src,
                home=jobdir,
                child_uid=child_uid,
                child_gid=child_gid,
            )
            task_started = child_started
            if src == APP and child_started:
                candidate_execution_started = True
            if src == APP:
                candidate_wall_seconds += wall
        except ChildLaunchError as exc:
            runner_launch_error = f"{type(exc).__name__}: {str(exc)[:500]}"
            child_output = f"runner launch exception: {runner_launch_error}"
        parsed_output, output_error, output_cleanup_error = _read_json_and_unlink(out, f"{role} output")
    except Exception as exc:
        unexpected_error = f"{type(exc).__name__}: {str(exc)[:500]}"
        if service_ready is not None and not task_started:
            runner_launch_error = runner_launch_error or unexpected_error
        else:
            service_error = unexpected_error
        child_output = f"runner/service exception: {unexpected_error}"
        if task_started:
            output_error = "output unavailable after runner/service exception"
    finally:
        if service_ready is not None:
            try:
                service_report = service.stop()
            except Exception as exc:
                stop_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                service_error = f"{service_error}; {stop_error}" if service_error else stop_error
                service.abort()
        else:
            service.abort()

    cleanup_errors = [error for error in (output_cleanup_error,) if error]
    try:
        db_hash_after = sha256(db)
        db_unchanged = db_hash_after == db_hash_before
    except OSError as exc:
        db_hash_after = None
        db_unchanged = False
        cleanup_errors.append(
            f"input database missing/unreadable: {type(exc).__name__}: {str(exc)[:180]}"
        )
    if not db_unchanged:
        cleanup_errors.append("input database was modified or replaced")
    try:
        _unlock_local_directories(jobroot)
        shutil.rmtree(jobroot)
    except OSError as exc:
        cleanup_errors.append(f"job directory cleanup failed: {type(exc).__name__}: {str(exc)[:180]}")
    try:
        if not PRIVILEGE_ISOLATION and os.path.isdir(socket_dir):
            os.chmod(socket_dir, 0o700)
        shutil.rmtree(socket_dir)
    except OSError as exc:
        cleanup_errors.append(
            f"meter socket directory cleanup failed: {type(exc).__name__}: {str(exc)[:180]}"
        )

    measurement_validity = "valid_model_outcome"
    if rc == RC_VERIFIER_BUDGET:
        measurement_validity = classify_causal_validity(
            "verifier_budget_exhausted",
            candidate_execution_started=candidate_execution_started,
        )
        service_error = service_error or "verifier work deadline exhausted"
    elif service_ready is None or (runner_launch_error is not None and not task_started):
        measurement_validity = "external_infra_invalid"
    elif (
        service_report is None
        or service_report.get("integrity_failures", 0)
        or not db_unchanged
    ):
        measurement_validity = "indeterminate_integrity"

    meter = service_report or {}
    guard_failure = "meter_policy_denial" if meter.get("policy_denials", 0) else None
    if rc == RC_ISOLATION:
        guard_failure = "process_isolation"
    elif rc == RC_OUTPUT_LIMIT:
        guard_failure = "child_output_limit"
    elif rc == RC_RESOURCE_LIMIT:
        guard_failure = "task_resource_limit"
    elif rc == RC_TIMEOUT or (
        src == APP and candidate_wall_seconds > CANDIDATE_TOTAL_WALL_SECONDS
    ):
        guard_failure = "task_timeout"
    error = None
    if runner_launch_error:
        error = f"runner launch error: {runner_launch_error}"
    elif service_error:
        error = f"meter service error: {service_error}"
    elif rc != 0:
        error = f"runner exited rc={rc}: {child_output[-800:]}"
    elif output_error:
        error = output_error
    elif not db_unchanged:
        error = "database_mutation: input database was modified or replaced"
    elif cleanup_errors:
        error = "; ".join(cleanup_errors)
    elif guard_failure:
        error = "database service rejected a prohibited operation"
    elif meter.get("requests_total", 0) < 1:
        error = "no metered database requests observed"

    data = {
        "ok": error is None and measurement_validity == "valid_model_outcome",
        "error": error,
        "queries": meter.get("requests_total"),
        "rows_delivered": meter.get("rows_delivered"),
        "response_bytes": meter.get("response_bytes"),
        "request_bytes": meter.get("request_bytes"),
        "vm_steps": meter.get("vm_steps"),
        "vm_progress_callbacks": meter.get("vm_progress_callbacks"),
        "seconds": round(wall, 4),
        "guard_failure": guard_failure,
        "connections_opened": meter.get("connections_accepted"),
        "child_cpu_seconds": round(cpu, 4),
        "peak_rss_raw": None,
        "peak_rss_raw_unit": None,
        "peak_rss_bytes": None,
        "result_parse_error": None,
        "output_parse_error": output_error,
        "cleanup_error": "; ".join(cleanup_errors) if cleanup_errors else None,
        "input_db_sha256_before": db_hash_before,
        "input_db_sha256_after": db_hash_after,
        "input_db_unchanged": db_unchanged,
        "measurement_validity": measurement_validity,
        "task_started": task_started,
        "attempt_id": attempt_id,
        "meter_ready": service_ready,
        "meter_report": service_report,
        "meter_error": service_error,
        "runner_launch_error": runner_launch_error,
        "month": month,
        "child_uid": child_uid if PRIVILEGE_ISOLATION else os.geteuid(),
        "rc": rc,
        "ext_seconds": round(wall, 4),
        "cpu_seconds": round(cpu, 4),
        "candidate_total_wall_seconds": (
            round(candidate_wall_seconds, 4) if src == APP else None
        ),
        "candidate_total_wall_limit_seconds": (
            CANDIDATE_TOTAL_WALL_SECONDS if src == APP else None
        ),
    }
    return data, parsed_output


def run_local_semantics_job(source_db, month, parent):
    """Exercise the submitted CLI against a local SQLite path as a black box.

    The pytest run is useful diagnosis but cannot be reward-authoritative because
    submitted modules share its interpreter.  This separate child receives only a
    read-only hidden database and output directory; the root verifier computes and
    compares the expected JSON after the child is gone.
    """
    global candidate_wall_seconds, candidate_execution_started
    jobroot = _prepare_job_root(parent, "run")
    jobdir = _prepare_child_dir(jobroot, "work", TASK_UID, TASK_GID)
    fixture_dir = os.path.join(jobroot, "fixture")
    os.mkdir(fixture_dir, 0o700)
    if PRIVILEGE_ISOLATION:
        os.chown(fixture_dir, 0, 0)
    runner = os.path.join(fixture_dir, "run_remote_export.py")
    database = os.path.join(fixture_dir, "input.db")
    _copy_child_readonly(os.path.join(TESTS, "run_remote_export.py"), runner)
    _copy_child_readonly(source_db, database)
    database_hash = sha256(database)
    os.chmod(fixture_dir, 0o555)
    # Parent directories deliberately do not exist: the CLI contract requires
    # creation of a missing nested output path.
    out = os.path.join(jobdir, "nested", "out", "statements.json")
    task_started = False
    runner_launch_error = None
    rc, child_output, wall, cpu = -1, "task was not started", 0.0, 0.0
    parsed_output = None
    output_error = "output unavailable"
    output_cleanup_error = None
    try:
        try:
            requested_timeout = min(
                RUN_TIMEOUT["n"],
                max(1.0, CANDIDATE_TOTAL_WALL_SECONDS - candidate_wall_seconds),
            )
            rc, child_output, wall, cpu, child_started = run(
                [sys.executable, "-I", runner, "--src", APP,
                 "--db", database, "--month", month, "--out", out],
                timeout=requested_timeout,
                cwd=jobdir,
                unprivileged=True,
                app=APP,
                home=jobdir,
                child_uid=TASK_UID,
                child_gid=TASK_GID,
            )
            task_started = child_started
            if child_started:
                candidate_execution_started = True
            candidate_wall_seconds += wall
        except ChildLaunchError as exc:
            runner_launch_error = f"{type(exc).__name__}: {str(exc)[:500]}"
            child_output = f"runner launch exception: {runner_launch_error}"
        parsed_output, output_error, output_cleanup_error = _read_json_and_unlink(
            out, "local-path output"
        )
        database_unchanged = sha256(database) == database_hash
        guard_failure = None
        if rc == RC_ISOLATION:
            guard_failure = "process_isolation"
        elif rc == RC_OUTPUT_LIMIT:
            guard_failure = "child_output_limit"
        elif rc == RC_RESOURCE_LIMIT:
            guard_failure = "task_resource_limit"
        elif rc == RC_TIMEOUT or candidate_wall_seconds > CANDIDATE_TOTAL_WALL_SECONDS:
            guard_failure = "task_timeout"
        error = None
        if runner_launch_error:
            error = f"runner launch error: {runner_launch_error}"
        elif rc != 0:
            error = f"runner exited rc={rc}: {child_output[-800:]}"
        elif output_error:
            error = output_error
        elif not database_unchanged:
            error = "database_mutation: local hidden database was modified or replaced"
        elif output_cleanup_error:
            error = output_cleanup_error
        if rc == RC_VERIFIER_BUDGET:
            measurement_validity = classify_causal_validity(
                "verifier_budget_exhausted",
                candidate_execution_started=candidate_execution_started,
            )
        elif runner_launch_error is not None and not task_started:
            measurement_validity = "external_infra_invalid"
        elif not database_unchanged:
            measurement_validity = "indeterminate_integrity"
        else:
            measurement_validity = "valid_model_outcome"
        return {
            "ok": error is None,
            "error": error,
            "measurement_validity": measurement_validity,
            "task_started": task_started,
            "guard_failure": guard_failure,
            "input_db_unchanged": database_unchanged,
            "input_db_sha256": database_hash,
            "output_parse_error": output_error,
            "output_cleanup_error": output_cleanup_error,
            "child_uid": TASK_UID if PRIVILEGE_ISOLATION else os.geteuid(),
            "rc": rc,
            "ext_seconds": round(wall, 4),
            "cpu_seconds": round(cpu, 4),
            "candidate_total_wall_seconds": round(candidate_wall_seconds, 4),
            "candidate_total_wall_limit_seconds": CANDIDATE_TOTAL_WALL_SECONDS,
        }, parsed_output
    finally:
        try:
            _unlock_local_directories(jobroot)
            shutil.rmtree(jobroot)
        except OSError:
            pass


def check_output(job, actual, expected):
    """Attach an interpretable equality/first-difference record to one job metric."""
    if job["output_parse_error"] is not None:
        matches = False
        difference = job["output_parse_error"]
    else:
        difference = first_json_difference(expected, actual)
        matches = difference is None
    job["output_matches_oracle"] = matches
    job["first_output_difference"] = difference
    return matches


def run_public_api_probe(parent):
    """Black-box the public helper and service APIs outside candidate-owned pytest."""

    global candidate_execution_started, candidate_wall_seconds
    value = -(100_000 + SENTINEL_SEED % 900_000)
    currencies = ("USD", "EUR", "GBP")
    currency = currencies[SENTINEL_SEED % len(currencies)]
    token = f"{SENTINEL_SEED & 0xFFFFFFFF:08x}"
    customer_id = 10_000 + SENTINEL_SEED % 80_000
    quantity = 2 + SENTINEL_SEED % 7
    unit_cents = 123 + SENTINEL_SEED % 4_000
    expected_amount = oracle.format_cents(quantity * unit_cents, currency)
    expected = {
        "formatted": oracle.format_cents(value, currency),
        "august_bounds": ["2026-08-01", "2026-09-01"],
        "december_bounds": ["2025-12-01", "2026-01-01"],
        "statements": [{
            "customer_id": customer_id,
            "name": f"Probe {token}",
            "email": f"{token}@probe.invalid",
            "invoice_count": 1,
            "invoices": [{
                "number": f"PROBE-{token}",
                "issued_on": "05 Aug 2026",
                "status": "open",
                "line_count": 1,
                "items": [{
                    "product": f"Widget {token}",
                    "quantity": quantity,
                    "amount": expected_amount,
                }],
                "amount": expected_amount,
            }],
            "total_due": expected_amount,
        }],
    }
    probe_dir = _prepare_child_dir(parent, "public-api-probe", TASK_UID, TASK_GID)
    probe_code = r'''
import json, sqlite3, sys
sys.path.insert(0, sys.argv[3])
from ledgerly.config import Settings
from ledgerly.domain.money import format_cents
from ledgerly.domain.window import month_bounds
from ledgerly.services.statements import StatementService

customer_id = int(sys.argv[4])
token = sys.argv[5]
quantity = int(sys.argv[6])
unit_cents = int(sys.argv[7])
currency = sys.argv[2]
conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, currency TEXT NOT NULL);
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL);
CREATE TABLE invoices (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, number TEXT NOT NULL, issued_at TEXT NOT NULL, discount_pct INTEGER, status TEXT NOT NULL);
CREATE TABLE line_items (id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL, product_id INTEGER NOT NULL, quantity INTEGER NOT NULL, unit_cents INTEGER NOT NULL);
CREATE INDEX idx_invoices_customer ON invoices(customer_id, issued_at);
CREATE INDEX idx_line_items_invoice ON line_items(invoice_id);
""")
conn.execute("INSERT INTO customers VALUES (?, ?, ?, ?)", (customer_id, f"Probe {token}", f"{token}@probe.invalid", currency))
conn.execute("INSERT INTO products VALUES (1, ?, ?)", (f"Widget {token}", f"SKU-{token}"))
conn.execute("INSERT INTO invoices VALUES (1, ?, ?, '2026-08-05T12:00:00', NULL, 'open')", (customer_id, f"PROBE-{token}"))
conn.execute("INSERT INTO line_items VALUES (1, 1, 1, ?, ?)", (quantity, unit_cents))
conn.commit()
print(json.dumps({
    "formatted": format_cents(int(sys.argv[1]), currency),
    "august_bounds": month_bounds("2026-08"),
    "december_bounds": month_bounds("2025-12"),
    "statements": StatementService(conn, Settings()).build("2026-08"),
}, ensure_ascii=False))
'''
    task_started = False
    launch_error = None
    rc, output, wall, cpu = -1, "task was not started", 0.0, 0.0
    try:
        try:
            rc, output, wall, cpu, child_started = run(
                [sys.executable, "-I", "-c", probe_code, str(value), currency, APP,
                 str(customer_id), token, str(quantity), str(unit_cents)],
                timeout=30,
                cwd=probe_dir,
                unprivileged=True,
                app=APP,
                home=probe_dir,
                child_uid=TASK_UID,
                child_gid=TASK_GID,
            )
            task_started = child_started
            if child_started:
                candidate_execution_started = True
            candidate_wall_seconds += wall
        except ChildLaunchError as exc:
            launch_error = f"{type(exc).__name__}: {str(exc)[:500]}"
        actual = None
        parse_error = None
        if rc == 0:
            try:
                actual = json.loads(output.strip().splitlines()[-1])
            except (IndexError, json.JSONDecodeError, TypeError, ValueError) as exc:
                parse_error = f"{type(exc).__name__}: {str(exc)[:180]}"
        guard_failure = None
        if rc == RC_ISOLATION:
            guard_failure = "process_isolation"
        elif rc == RC_OUTPUT_LIMIT:
            guard_failure = "child_output_limit"
        elif rc == RC_RESOURCE_LIMIT:
            guard_failure = "task_resource_limit"
        elif rc == RC_TIMEOUT:
            guard_failure = "task_timeout"
        if rc == RC_VERIFIER_BUDGET:
            measurement_validity = classify_causal_validity(
                "verifier_budget_exhausted",
                candidate_execution_started=candidate_execution_started,
            )
        elif launch_error is not None and not task_started:
            measurement_validity = "external_infra_invalid"
        else:
            measurement_validity = "valid_model_outcome"
        return {
            "input_cents": value,
            "currency": currency,
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "expected": expected,
            "actual": actual,
            "parse_error": parse_error,
            "rc": rc,
            "guard_failure": guard_failure,
            "task_started": task_started,
            "measurement_validity": measurement_validity,
            "launch_error": launch_error,
            "seconds": round(wall, 4),
            "cpu_seconds": round(cpu, 4),
            "matches": actual == expected,
        }
    finally:
        try:
            _unlock_local_directories(probe_dir)
            shutil.rmtree(probe_dir)
        except OSError:
            pass


def _table_counts(path):
    conn = sqlite3.connect(path)
    try:
        return {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("customers", "products", "invoices", "line_items")
        }
    finally:
        conn.close()


def _build_semantic_sentinel(parent):
    """Build a compact secret-shifted DB that deterministically covers semantics.

    Random generator fixtures are valuable distribution samples but cannot promise
    rare ordering/finance cases in one run.  This control combines those cases in a
    root-owned database.  Secret-shifted IDs and labels prevent a fixed public output
    blob from satisfying it, while the schema and semantic motifs remain declared.
    """

    rng = random.Random(SENTINEL_SEED)
    customer_base = rng.randrange(10_000, 90_000) * 10
    invoice_base = rng.randrange(100_000, 900_000) * 100
    line_base = rng.randrange(100_000, 900_000) * 100
    token = f"{rng.randrange(0, 16**8):08x}"
    customer_ids = {
        "main": customer_base + 10,
        "deleted": customer_base + 20,
        "empty": customer_base + 30,
        "signed": customer_base + 40,
    }

    path = os.path.join(parent, f"semantic-sentinel-{uuid.uuid4().hex}.db")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
                currency TEXT NOT NULL
            );
            CREATE TABLE products (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL
            );
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
                number TEXT NOT NULL, issued_at TEXT NOT NULL,
                discount_pct INTEGER, status TEXT NOT NULL
            );
            CREATE TABLE line_items (
                id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                product_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
                unit_cents INTEGER NOT NULL
            );
            CREATE INDEX idx_invoices_customer ON invoices(customer_id, issued_at);
            CREATE INDEX idx_line_items_invoice ON line_items(invoice_id);
            """
        )
        # Deliberately insert parent rows out of semantic order.
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?)",
            [
                (customer_ids["empty"], f"Zoë 王 {token}", "empty@example.test", "EUR"),
                (customer_ids["main"], f"Mateo García {token}", "main@example.test", "USD"),
                (customer_ids["signed"], f"Large Value {token}", "large@example.test", "EUR"),
                (customer_ids["deleted"], f"Ólafur Björk {token}", "deleted@example.test", "GBP"),
            ],
        )
        conn.executemany(
            "INSERT INTO products VALUES (?, ?, ?)",
            [
                (4, f"Onboarding {token}", "SKU-4"),
                (1, f"Consulting Ω {token}", "SKU-1"),
                (5, f"API calls {token}", "SKU-5"),
                (2, f"Seat license {token}", "SKU-2"),
                (3, f"Support plan {token}", "SKU-3"),
            ],
        )

        def inv(offset, customer, issued, discount, status):
            identifier = invoice_base + offset
            return (
                identifier,
                customer_ids[customer],
                f"INV-{token}-{offset:04d}",
                issued,
                discount,
                status,
            )

        invoices = [
            inv(300, "main", "2026-08-10T00:00:00", 0, "paid"),
            inv(100, "main", "2026-08-10T00:00:00", None, "paid"),
            inv(200, "main", "2026-08-09T23:00:00", None, "open"),
            inv(400, "main", "2026-08-11T00:00:00", 15, "open"),
            inv(500, "main", "2026-08-12T00:00:00", None, "void"),
            inv(600, "main", "2026-08-13T00:00:00", 10, "paid"),
            inv(700, "deleted", "2026-08-05T00:00:00", None, "paid"),
            inv(720, "signed", "2026-08-07T00:00:00", None, "open"),
            inv(800, "main", "2026-08-01T00:00:00", None, "paid"),
            inv(850, "main", "2026-08-31T23:59:59", None, "paid"),
            inv(900, "main", "2026-09-01T00:00:00", None, "paid"),
            inv(901, "main", "2026-07-31T23:59:59", None, "paid"),
            inv(1000, "main", "2025-12-31T23:59:59", None, "paid"),
            inv(1001, "main", "2026-01-01T00:00:00", None, "paid"),
        ]
        conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", invoices)

        def line(offset, invoice_offset, product, quantity, unit_cents):
            return (
                line_base + offset,
                invoice_base + invoice_offset,
                product,
                quantity,
                unit_cents,
            )

        lines = [
            # NULL discount behaves as zero on the same 10.00 subtotal as invoice 300.
            line(5, 100, 1, 1, 1000),
            # Duplicate product rows both count.
            line(1, 200, 2, 1, 5000),
            line(2, 200, 2, 1, 5000),
            # IDs, products, and insertion order disagree; ID order is authoritative.
            line(30, 300, 1, 1, 100),
            line(10, 300, 4, 1, 200),
            line(20, 300, 9, 1, 300),
            line(40, 300, 2, 1, 400),
            # Missing product on a void invoice still appears but is not owed.
            line(50, 500, 404, 3, 700),
            # Invoice-level discount: 1001 - floor(1001*10/100) = 901.
            line(61, 600, 1, 1, 333),
            line(62, 600, 2, 1, 333),
            line(63, 600, 3, 1, 335),
            # Invoice whose only product is retired.
            line(70, 700, 404, 3, 700),
            # Large arithmetic/formatting value.
            line(72, 720, 1, 20, 50000),
            # Inclusive start / exclusive end and December rollover controls.
            line(80, 800, 5, 1, 250),
            line(85, 850, 5, 1, 175),
            line(90, 900, 5, 1, 999),
            line(91, 901, 5, 1, 888),
            line(100, 1000, 5, 1, 123),
            line(101, 1001, 5, 1, 456),
        ]
        conn.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?)", lines)
        conn.commit()
    finally:
        conn.close()
    if PRIVILEGE_ISOLATION:
        os.chown(path, 0, 0)
    os.chmod(path, 0o600)
    return path, {
        "seed": SENTINEL_SEED,
        "token": token,
        "months": ["2026-08", "2025-12"],
        "customer_ids": customer_ids,
        "invoice_numbers": {
            str(offset): f"INV-{token}-{offset:04d}"
            for offset in (
                100, 200, 300, 400, 500, 600, 700, 720,
                800, 850, 900, 901, 1000, 1001
            )
        },
        "counts": _table_counts(path),
        "sha256": sha256(path),
        "covered_motifs": [
            "customer/invoice/line ordering",
            "inclusive-start/exclusive-end month boundary",
            "December year rollover",
            "invoice-level rounding",
            "NULL and zero discounts",
            "empty customer and empty invoice",
            "void invoice",
            "duplicate line rows",
            "retired product references",
            "Unicode",
            "large money formatting",
        ],
    }


def _assert_semantic_sentinel_fixture(path, metadata):
    """Validate raw fixture facts before trusting oracle-derived output checks."""

    if metadata["counts"] != {
        "customers": 4,
        "products": 5,
        "invoices": 14,
        "line_items": 19,
    }:
        raise RuntimeError(
            f"semantic sentinel raw counts drifted: {metadata['counts']}"
        )
    numbers = metadata["invoice_numbers"]
    conn = sqlite3.connect(path)
    try:
        invoices = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT number, id, issued_at, discount_pct FROM invoices"
            )
        }
        expected_boundaries = {
            numbers["800"]: "2026-08-01T00:00:00",
            numbers["850"]: "2026-08-31T23:59:59",
            numbers["900"]: "2026-09-01T00:00:00",
            numbers["901"]: "2026-07-31T23:59:59",
            numbers["1000"]: "2025-12-31T23:59:59",
            numbers["1001"]: "2026-01-01T00:00:00",
        }
        if any(
            invoices.get(number, (None, None, None))[1] != issued_at
            for number, issued_at in expected_boundaries.items()
        ):
            raise RuntimeError("semantic sentinel raw boundary controls drifted")
        null_invoice = invoices[numbers["100"]]
        zero_invoice = invoices[numbers["300"]]
        if null_invoice[2] is not None or zero_invoice[2] != 0:
            raise RuntimeError("semantic sentinel raw NULL/zero discounts drifted")
        for invoice in (null_invoice, zero_invoice):
            if conn.execute(
                "SELECT count(*) FROM line_items WHERE invoice_id = ?", (invoice[0],)
            ).fetchone()[0] < 1:
                raise RuntimeError("semantic sentinel discount control is empty")
        ordered_product_ids = [
            row[0]
            for row in conn.execute(
                "SELECT product_id FROM line_items WHERE invoice_id = ? ORDER BY id",
                (zero_invoice[0],),
            )
        ]
        if ordered_product_ids != [4, 9, 1, 2]:
            raise RuntimeError("semantic sentinel raw line-order control drifted")
        if conn.execute("SELECT count(*) FROM products WHERE id = 404").fetchone()[0]:
            raise RuntimeError("semantic sentinel retired product unexpectedly exists")
        if conn.execute(
            "SELECT count(*) FROM line_items WHERE product_id = 404"
        ).fetchone()[0] != 2:
            raise RuntimeError("semantic sentinel retired-product references drifted")
    finally:
        conn.close()


def _assert_semantic_sentinel_landmarks(actual, metadata, month):
    """Prove the trusted control really instantiates every claimed rare motif."""

    statements = actual.get("statements") if isinstance(actual, dict) else None
    if not isinstance(statements, list):
        raise RuntimeError("semantic sentinel oracle did not return statements")
    ids = metadata["customer_ids"]
    numbers = metadata["invoice_numbers"]
    if [statement["customer_id"] for statement in statements] != sorted(ids.values()):
        raise RuntimeError("semantic sentinel does not exercise customer ordering")
    by_customer = {statement["customer_id"]: statement for statement in statements}
    expected_statement_keys = {
        "customer_id", "name", "email", "invoice_count", "invoices", "total_due"
    }
    if any(set(statement) != expected_statement_keys for statement in statements):
        raise RuntimeError("semantic sentinel customer output shape failed")
    if by_customer[ids["empty"]]["invoice_count"] != 0:
        raise RuntimeError("semantic sentinel empty-customer landmark failed")
    main = by_customer[ids["main"]]
    observed_numbers = [invoice["number"] for invoice in main["invoices"]]
    if month == "2026-08":
        expected_order = [
            numbers[str(offset)]
            for offset in (800, 200, 100, 300, 400, 500, 600, 850)
        ]
        if observed_numbers != expected_order:
            raise RuntimeError("semantic sentinel invoice ordering/boundary landmark failed")
        invoices = {invoice["number"]: invoice for invoice in main["invoices"]}
        if invoices[numbers["400"]]["amount"] != "0.00 USD":
            raise RuntimeError("semantic sentinel empty-invoice landmark failed")
        if invoices[numbers["600"]]["amount"] != "9.01 USD":
            raise RuntimeError("semantic sentinel invoice-rounding landmark failed")
        if [item["amount"] for item in invoices[numbers["600"]]["items"]] != [
            "3.33 USD", "3.33 USD", "3.35 USD"
        ]:
            raise RuntimeError("semantic sentinel pre-discount item amounts failed")
        if (
            invoices[numbers["100"]]["amount"] != "10.00 USD"
            or invoices[numbers["300"]]["amount"] != "10.00 USD"
        ):
            raise RuntimeError("semantic sentinel NULL/zero discount landmark failed")
        duplicate = invoices[numbers["200"]]
        if duplicate["line_count"] != 2 or len(duplicate["items"]) != 2:
            raise RuntimeError("semantic sentinel duplicate-line landmark failed")
        ordered_items = [
            item["product"] for item in invoices[numbers["300"]]["items"]
        ]
        if ordered_items != [
            f"Onboarding {metadata['token']}",
            oracle.UNKNOWN_PRODUCT,
            f"Consulting Ω {metadata['token']}",
            f"Seat license {metadata['token']}",
        ]:
            raise RuntimeError("semantic sentinel line-order/retired-product landmark failed")
        if (
            invoices[numbers["500"]]["status"] != "void"
            or invoices[numbers["500"]]["amount"] != "21.00 USD"
            or main["total_due"] != "133.26 USD"
        ):
            raise RuntimeError("semantic sentinel void landmark failed")
        deleted = by_customer[ids["deleted"]]["invoices"]
        if (
            len(deleted) != 1
            or deleted[0]["items"] != [{
                "product": oracle.UNKNOWN_PRODUCT,
                "quantity": 3,
                "amount": "21.00 GBP",
            }]
            or by_customer[ids["deleted"]]["total_due"] != "21.00 GBP"
        ):
            raise RuntimeError("semantic sentinel deleted-only invoice landmark failed")
        signed = by_customer[ids["signed"]]
        amounts = [item["amount"] for inv in signed["invoices"] for item in inv["items"]]
        if amounts != ["10,000.00 EUR"]:
            raise RuntimeError("semantic sentinel large-money landmark failed")
        if metadata["token"] not in by_customer[ids["empty"]]["name"]:
            raise RuntimeError("semantic sentinel Unicode/secret label landmark failed")
    elif month == "2025-12":
        if (
            observed_numbers != [numbers["1000"]]
            or main["invoices"][0]["amount"] != "1.23 USD"
            or main["total_due"] != "1.23 USD"
        ):
            raise RuntimeError("semantic sentinel December rollover landmark failed")
    else:
        raise RuntimeError(f"unexpected semantic sentinel month: {month}")


def _inject_representative_semantic_motifs(path, month, seed):
    """Add rare semantic controls to an otherwise representative n/8n fixture."""

    rng = random.Random(seed ^ SENTINEL_SEED)
    token = f"{rng.randrange(0, 16**10):010x}"
    start, end = oracle.month_bounds(month)
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    at = lambda days: (start_dt + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = sqlite3.connect(path)
    try:
        customer_base = conn.execute(
            "SELECT coalesce(max(id), 0) + 100 FROM customers"
        ).fetchone()[0]
        invoice_base = conn.execute(
            "SELECT coalesce(max(id), 0) + 1000 FROM invoices"
        ).fetchone()[0]
        line_base = conn.execute(
            "SELECT coalesce(max(id), 0) + 1000 FROM line_items"
        ).fetchone()[0]
        product_base = conn.execute(
            "SELECT coalesce(max(id), 0) + 100 FROM products"
        ).fetchone()[0]
        customers = {
            "main": customer_base + 10,
            "deleted": customer_base + 20,
            "empty": customer_base + 30,
            "signed": customer_base + 40,
        }
        products = {name: product_base + index for index, name in enumerate(
            ("consulting", "seat", "support", "onboarding", "api"), start=1
        )}
        missing_product = product_base + 9999
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?)",
            [
                (customers["empty"], f"Zoë 王 {token}", "empty@hidden.test", "EUR"),
                (customers["main"], f"Mateo García {token}", "main@hidden.test", "USD"),
                (customers["signed"], f"Large Value {token}", "large@hidden.test", "EUR"),
                (customers["deleted"], f"Ólafur Björk {token}", "deleted@hidden.test", "GBP"),
            ],
        )
        conn.executemany(
            "INSERT INTO products VALUES (?, ?, ?)",
            [
                (products["onboarding"], f"Onboarding {token}", f"H-{token}-4"),
                (products["consulting"], f"Consulting Ω {token}", f"H-{token}-1"),
                (products["api"], f"API calls {token}", f"H-{token}-5"),
                (products["seat"], f"Seat license {token}", f"H-{token}-2"),
                (products["support"], f"Support plan {token}", f"H-{token}-3"),
            ],
        )

        def invoice(offset, customer, issued, discount, status):
            return (
                invoice_base + offset,
                customers[customer],
                f"HINV-{token}-{offset:04d}",
                issued,
                discount,
                status,
            )

        invoice_rows = [
            invoice(300, "main", at(9), 0, "paid"),
            invoice(100, "main", at(9), None, "paid"),
            invoice(200, "main", at(8), None, "open"),
            invoice(400, "main", at(10), 15, "open"),
            invoice(500, "main", at(11), None, "void"),
            invoice(600, "main", at(12), 10, "paid"),
            invoice(700, "deleted", at(4), None, "paid"),
            invoice(720, "signed", at(6), None, "open"),
            invoice(800, "main", start + "T00:00:00", None, "paid"),
            invoice(
                850,
                "main",
                (end_dt - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S"),
                None,
                "paid",
            ),
            invoice(900, "main", end + "T00:00:00", None, "paid"),
            invoice(
                901,
                "main",
                (start_dt - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S"),
                None,
                "paid",
            ),
        ]
        conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", invoice_rows)

        def line(offset, invoice_offset, product, quantity, unit_cents):
            return (
                line_base + offset,
                invoice_base + invoice_offset,
                product,
                quantity,
                unit_cents,
            )

        line_rows = [
            line(5, 100, products["consulting"], 1, 1000),
            line(1, 200, products["seat"], 1, 5000),
            line(2, 200, products["seat"], 1, 5000),
            line(30, 300, products["consulting"], 1, 100),
            line(10, 300, products["onboarding"], 1, 200),
            line(20, 300, missing_product, 1, 300),
            line(40, 300, products["seat"], 1, 400),
            line(50, 500, missing_product, 3, 700),
            line(61, 600, products["consulting"], 1, 333),
            line(62, 600, products["seat"], 1, 333),
            line(63, 600, products["support"], 1, 335),
            line(70, 700, missing_product, 3, 700),
            line(72, 720, products["consulting"], 20, 50000),
            line(80, 800, products["api"], 1, 250),
            line(85, 850, products["api"], 1, 175),
            line(90, 900, products["api"], 1, 999),
            line(91, 901, products["api"], 1, 888),
        ]
        conn.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?)", line_rows)
        conn.commit()
    finally:
        conn.close()
    return {
        "token": token,
        "month": month,
        "customer_ids": customers,
        "invoice_numbers": {
            str(offset): f"HINV-{token}-{offset:04d}"
            for offset in (
                100, 200, 300, 400, 500, 600, 700, 720, 800, 850, 900, 901
            )
        },
        "invoice_base": invoice_base,
        "line_base": line_base,
        "product_ids": products,
        "missing_product_id": missing_product,
        "month_start": start,
        "month_end": end,
        "sha256_after_injection": sha256(path),
    }


def _assert_representative_semantic_landmarks(actual, metadata):
    statements = actual.get("statements") if isinstance(actual, dict) else None
    if not isinstance(statements, list):
        raise RuntimeError("representative oracle did not return statements")
    ids = metadata["customer_ids"]
    numbers = metadata["invoice_numbers"]
    by_customer = {statement["customer_id"]: statement for statement in statements}
    if not set(ids.values()).issubset(by_customer):
        raise RuntimeError("representative semantic customers are missing")
    if by_customer[ids["empty"]]["invoice_count"] != 0:
        raise RuntimeError("representative empty-customer landmark failed")
    main = by_customer[ids["main"]]
    expected_order = [
        numbers[str(offset)]
        for offset in (800, 200, 100, 300, 400, 500, 600, 850)
    ]
    if [invoice["number"] for invoice in main["invoices"]] != expected_order:
        raise RuntimeError("representative ordering/boundary landmark failed")
    invoices = {invoice["number"]: invoice for invoice in main["invoices"]}
    if invoices[numbers["400"]]["amount"] != "0.00 USD":
        raise RuntimeError("representative empty-invoice landmark failed")
    if invoices[numbers["600"]]["amount"] != "9.01 USD":
        raise RuntimeError("representative invoice-rounding landmark failed")
    if [item["amount"] for item in invoices[numbers["600"]]["items"]] != [
        "3.33 USD", "3.33 USD", "3.35 USD"
    ]:
        raise RuntimeError("representative pre-discount item amounts failed")
    if (
        invoices[numbers["100"]]["amount"] != "10.00 USD"
        or invoices[numbers["300"]]["amount"] != "10.00 USD"
    ):
        raise RuntimeError("representative NULL/zero discount landmark failed")
    if invoices[numbers["200"]]["line_count"] != 2:
        raise RuntimeError("representative duplicate-line landmark failed")
    expected_products = [
        f"Onboarding {metadata['token']}",
        oracle.UNKNOWN_PRODUCT,
        f"Consulting Ω {metadata['token']}",
        f"Seat license {metadata['token']}",
    ]
    if [item["product"] for item in invoices[numbers["300"]]["items"]] != expected_products:
        raise RuntimeError("representative line-order/retired-product landmark failed")
    deleted = by_customer[ids["deleted"]]["invoices"]
    if (
        len(deleted) != 1
        or deleted[0]["items"] != [{
            "product": oracle.UNKNOWN_PRODUCT,
            "quantity": 3,
            "amount": "21.00 GBP",
        }]
        or by_customer[ids["deleted"]]["total_due"] != "21.00 GBP"
    ):
        raise RuntimeError("representative deleted-only landmark failed")
    large_amounts = [
        item["amount"]
        for invoice in by_customer[ids["signed"]]["invoices"]
        for item in invoice["items"]
    ]
    if large_amounts != ["10,000.00 EUR"]:
        raise RuntimeError("representative large-money landmark failed")
    if (
        invoices[numbers["500"]]["status"] != "void"
        or invoices[numbers["500"]]["amount"] != "21.00 USD"
        or main["total_due"] != "133.26 USD"
    ):
        raise RuntimeError("representative void/total landmark failed")


def _assert_representative_fixture_landmarks(path, metadata):
    """Check injected raw facts independently of the output oracle."""

    before = metadata["counts_before_injection"]
    after = metadata["counts_after_injection"]
    expected_delta = {
        "customers": 4,
        "products": 5,
        "invoices": 12,
        "line_items": 17,
    }
    observed_delta = {key: after[key] - before[key] for key in expected_delta}
    if observed_delta != expected_delta:
        raise RuntimeError(
            f"representative semantic injection counts drifted: {observed_delta}"
        )
    numbers = metadata["invoice_numbers"]
    conn = sqlite3.connect(path)
    try:
        invoices = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT number, id, issued_at, discount_pct FROM invoices "
                "WHERE number LIKE ?",
                (f"HINV-{metadata['token']}-%",),
            )
        }
        start = metadata["month_start"]
        end = metadata["month_end"]
        end_minus_one = (
            datetime.strptime(end, "%Y-%m-%d") - timedelta(seconds=1)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        start_minus_one = (
            datetime.strptime(start, "%Y-%m-%d") - timedelta(seconds=1)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        expected_boundaries = {
            numbers["800"]: start + "T00:00:00",
            numbers["850"]: end_minus_one,
            numbers["900"]: end + "T00:00:00",
            numbers["901"]: start_minus_one,
        }
        if any(
            invoices.get(number, (None, None, None))[1] != issued_at
            for number, issued_at in expected_boundaries.items()
        ):
            raise RuntimeError("representative raw boundary controls drifted")
        null_invoice = invoices[numbers["100"]]
        zero_invoice = invoices[numbers["300"]]
        if null_invoice[2] is not None or zero_invoice[2] != 0:
            raise RuntimeError("representative raw NULL/zero discounts drifted")
        if any(
            conn.execute(
                "SELECT count(*) FROM line_items WHERE invoice_id = ?", (row[0],)
            ).fetchone()[0] < 1
            for row in (null_invoice, zero_invoice)
        ):
            raise RuntimeError("representative discount control is empty")
        ordered_products = [
            row[0]
            for row in conn.execute(
                "SELECT product_id FROM line_items WHERE invoice_id = ? ORDER BY id",
                (zero_invoice[0],),
            )
        ]
        products = metadata["product_ids"]
        if ordered_products != [
            products["onboarding"],
            metadata["missing_product_id"],
            products["consulting"],
            products["seat"],
        ]:
            raise RuntimeError("representative raw line-order control drifted")
        if conn.execute(
            "SELECT count(*) FROM products WHERE id = ?",
            (metadata["missing_product_id"],),
        ).fetchone()[0]:
            raise RuntimeError("representative retired product unexpectedly exists")
    finally:
        conn.close()


def _add_irrelevant_history(source, destination):
    """Copy `source`, then add deterministic 2014--2023 history only."""
    shutil.copyfile(source, destination)
    conn = sqlite3.connect(destination)
    inserted_invoices = 0
    inserted_lines = 0
    try:
        customer_ids = [row[0] for row in conn.execute("SELECT id FROM customers ORDER BY id")]
        if len(customer_ids) != HISTORY_CUSTOMERS:
            raise RuntimeError(f"history fixture expected {HISTORY_CUSTOMERS} customers, got {len(customer_ids)}")
        next_invoice = conn.execute("SELECT coalesce(max(id), 0) + 1 FROM invoices").fetchone()[0]
        next_line = conn.execute("SELECT coalesce(max(id), 0) + 1 FROM line_items").fetchone()[0]
        product_count = conn.execute("SELECT count(*) FROM products").fetchone()[0]
        if product_count < 1:
            raise RuntimeError("history fixture has no products")
        invoice_batch = []
        line_batch = []

        def flush():
            nonlocal inserted_invoices, inserted_lines
            if invoice_batch:
                conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", invoice_batch)
                inserted_invoices += len(invoice_batch)
                invoice_batch.clear()
            if line_batch:
                conn.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?)", line_batch)
                inserted_lines += len(line_batch)
                line_batch.clear()

        with conn:
            for customer_id in customer_ids:
                for sequence in range(HISTORY_INVOICES_PER_CUSTOMER):
                    invoice_id = next_invoice
                    next_invoice += 1
                    year = 2014 + sequence % 10
                    month = 1 + ((customer_id * 7 + sequence * 5) % 12)
                    day = 1 + ((customer_id + sequence * 11) % 28)
                    invoice_batch.append((
                        invoice_id,
                        customer_id,
                        f"HIST-{customer_id:05d}-{sequence:04d}",
                        f"{year:04d}-{month:02d}-{day:02d}T12:34:56",
                        None if sequence % 4 == 0 else (sequence * 7) % 31,
                        ("paid", "open", "void")[sequence % 3],
                    ))
                    for item in range(HISTORY_LINES_PER_INVOICE):
                        product_id = 1 + ((customer_id * 17 + sequence * 13 + item * 19) % product_count)
                        line_batch.append((
                            next_line,
                            invoice_id,
                            product_id,
                            1 + item % 5,
                            100 + ((customer_id + sequence + item) % 49900),
                        ))
                        next_line += 1
                    if len(invoice_batch) >= 2000:
                        flush()
            flush()
        conn.commit()
    finally:
        conn.close()
    expected_invoices = HISTORY_CUSTOMERS * HISTORY_INVOICES_PER_CUSTOMER
    expected_lines = expected_invoices * HISTORY_LINES_PER_INVOICE
    if (inserted_invoices, inserted_lines) != (expected_invoices, expected_lines):
        raise RuntimeError(
            f"history fixture inserted {(inserted_invoices, inserted_lines)}, "
            f"expected {(expected_invoices, expected_lines)}"
        )
    return {"added_invoices": inserted_invoices, "added_line_items": inserted_lines}


def _build_history_pair(parent, generator):
    """Create a clean/history metamorphic pair and independently prove equal output."""
    base = os.path.join(parent, f"history-base-{uuid.uuid4().hex}.db")
    history = os.path.join(parent, f"history-twin-{uuid.uuid4().hex}.db")
    history_seed = HISTORY_CASE["seed"]
    history_month = HISTORY_CASE["month"]
    rc, output, _, _, _ = run(
        [sys.executable, "-I", generator, "--out", base, "--seed", str(history_seed),
         "--customers", str(HISTORY_CUSTOMERS), "--month", history_month] + _SHAPE,
        timeout=300,
        cwd=parent,
    )
    if rc == RC_VERIFIER_BUDGET:
        raise VerifierBudgetExhausted(
            "verifier work deadline exhausted during history fixture generation"
        )
    if rc != 0:
        raise RuntimeError(f"history base generator failed: {output[-500:]}")
    base_counts = _table_counts(base)
    additions = _add_irrelevant_history(base, history)
    history_counts = _table_counts(history)
    expected = oracle.compute(base, history_month)
    history_expected = oracle.compute(history, history_month)
    oracle_equal = first_json_difference(expected, history_expected) is None
    del history_expected
    for path in (base, history):
        if PRIVILEGE_ISOLATION:
            os.chown(path, 0, 0)
        os.chmod(path, 0o600)
    fixture = {
        "month": history_month,
        "seed": history_seed,
        "customers": HISTORY_CUSTOMERS,
        "invoices_per_customer_added": HISTORY_INVOICES_PER_CUSTOMER,
        "lines_per_added_invoice": HISTORY_LINES_PER_INVOICE,
        "base_counts": base_counts,
        "history_counts": history_counts,
        **additions,
        "base_sha256": sha256(base),
        "history_sha256": sha256(history),
        "base_bytes": os.path.getsize(base),
        "history_bytes": os.path.getsize(history),
        "oracle_outputs_equal": oracle_equal,
        "generator_tail": output.strip()[-200:],
    }
    if not oracle_equal:
        raise RuntimeError("irrelevant history changed the independent oracle output")
    return base, history, expected, fixture


def _coefficient_of_variation(values):
    """Sample CV for diagnostics; zero for a singleton or exact-zero series."""
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    return 0.0 if mean == 0 else statistics.stdev(values) / mean


# ---------------------------------------------------------------- 1. tamper
if SEED_CONFIGURATION_ERROR:
    metrics["notes"].append(SEED_CONFIGURATION_ERROR)
    finish(0, "verifier_error")
if not PRIVILEGE_ISOLATION and not LOCAL_COMPATIBILITY:
    metrics["notes"].append(
        "official verifier execution requires root isolation; same-UID scoring is disabled"
    )
    finish(0, "verifier_isolation_failed")

os.makedirs(LOGS, exist_ok=True)
if PRIVILEGE_ISOLATION:
    os.chown(LOGS, 0, 0)
    os.chmod(LOGS, 0o700)
shared_scratch_modes = _lock_shared_scratch()
artifact_problems = _validate_and_lock_app()
metrics["checks"]["privilege_isolation"] = {
    "enabled": PRIVILEGE_ISOLATION,
    "task_uid": TASK_UID if PRIVILEGE_ISOLATION else os.geteuid(),
    "task_gid": TASK_GID if PRIVILEGE_ISOLATION else os.getegid(),
    "tests_mode": oct(stat.S_IMODE(os.stat(TESTS).st_mode)),
    "logs_mode": oct(stat.S_IMODE(os.stat(LOGS).st_mode)) if os.path.exists(LOGS) else None,
    "live_evidence_path": LOGS,
    "publication_path": PUBLISH_LOGS,
    "publication_path_untrusted_until_epilogue": not LOCAL_COMPATIBILITY,
    "shared_scratch_modes": shared_scratch_modes,
    "artifact_read_only": PRIVILEGE_ISOLATION and not artifact_problems,
    "artifact_problems": artifact_problems,
    "task_resource_limits": {
        "cpu_seconds": TASK_CPU_SECONDS,
        "address_space_bytes": TASK_ADDRESS_SPACE_BYTES,
        "file_bytes": TASK_FILE_BYTES,
        "job_directory_bytes": TASK_JOBDIR_BYTES,
        "job_directory_entries": TASK_JOBDIR_ENTRIES,
        "open_files": TASK_OPEN_FILES,
        "processes": TASK_PROCESSES,
    },
}
if artifact_problems:
    finish(0, "unsafe_artifact")

workdir = _prepare_private_workdir()
atexit.register(lambda: shutil.rmtree(workdir, ignore_errors=True))
isolation_probe = _probe_privilege_boundary(workdir)
metrics["checks"]["privilege_isolation"]["probe"] = isolation_probe
if PRIVILEGE_ISOLATION:
    required_probe = {
        "uid": TASK_UID,
        "gid": TASK_GID,
        "tests_read_denied": True,
        "tests_write_denied": True,
        "logs_read_denied": True,
        "logs_write_denied": True,
        "app_write_denied": True,
        "parent_read_denied": True,
        "parent_write_denied": True,
        "signal_parent_denied": True,
        "global_tmp_list_denied": True,
        "global_tmp_write_denied": True,
        "shared_memory_write_denied": True,
        "message_queue_write_denied": True,
        "run_lock_write_denied": True,
        "proc_parent_environ_read_denied": True,
        "proc_parent_mem_read_denied": True,
        "proc_parent_fd_list_denied": True,
        "proc_parent_fd0_readlink_denied": True,
        "proc_parent_cwd_readlink_denied": True,
        "no_new_privs": 1,
        "dedicated_dir_write_ok": True,
        "rc": 0,
    }
    if any(isolation_probe.get(key) != value for key, value in required_probe.items()):
        finish(0, "verifier_isolation_failed")

tamper = {}
for name in ("gen_data.py", "run_visible.sh", "visible_sqlite_service.py"):
    agent_copy = os.path.join(APP, "workloads", name)
    pristine = os.path.join(PRISTINE_WORKLOADS, name)
    try:
        agent_info = os.lstat(agent_copy)
        agent_mode = stat.filemode(agent_info.st_mode)
        agent_hash = sha256(agent_copy) if stat.S_ISREG(agent_info.st_mode) else None
        stat_error = None
    except OSError as exc:
        agent_mode = None
        agent_hash = None
        stat_error = f"{type(exc).__name__}: {exc}"
    tamper[name] = {"pristine": sha256(pristine), "agent": agent_hash,
                    "agent_mode": agent_mode, "stat_error": stat_error}
    tamper[name]["changed"] = tamper[name]["agent"] != tamper[name]["pristine"]
    os.makedirs(os.path.dirname(agent_copy), exist_ok=True)
    _restore_pristine(pristine, agent_copy)  # restore without following an agent-controlled path
metrics["checks"]["tamper"] = tamper
if any(v["changed"] for v in tamper.values()):
    finish(0, "tampered_workload")

# ---------------------------------------------------------------- 2. correctness
require_verifier_budget("diagnostic pytest", 65.0)
with open(SUITE, encoding="utf-8") as fh:
    expected_tests = sum(1 for line in fh if line.startswith("def test_"))
correctness_dir = _prepare_child_dir(workdir, "correctness")
suite_copy = os.path.join(correctness_dir, "test_statements.py")
ini_copy = os.path.join(correctness_dir, "pytest.ini")
_copy_child_readonly(SUITE, suite_copy)
_copy_child_readonly(os.path.join(TESTS, "pytest.ini"), ini_copy)
junit = os.path.join(correctness_dir, "junit.xml")
rc, output, _, _, diagnostic_started = run(
    [sys.executable, "-I", "-m", "pytest", "-q", "--tb=short",
     "-c", ini_copy, "-o", "addopts=", "-p", "no:cacheprovider",
     "--confcutdir", correctness_dir, "--rootdir", correctness_dir,
     "--junitxml", junit, suite_copy],
    timeout=60,
    cwd=correctness_dir,
    unprivileged=True,
    app=APP,
    home=correctness_dir,
)
if diagnostic_started:
    candidate_execution_started = True
if rc == RC_VERIFIER_BUDGET:
    metrics["notes"].append("verifier work deadline exhausted during diagnostic pytest")
    finish(0, "verifier_budget_exhausted")
if rc == RC_ISOLATION:
    finish(0, "process_isolation")
if rc == RC_OUTPUT_LIMIT:
    finish(0, "child_output_limit")
if rc == RC_RESOURCE_LIMIT:
    finish(0, "task_resource_limit")
counts = {"tests": None, "failures": None, "errors": None, "skipped": None}
element_counts = {"testcases": None, "failure_nodes": None, "error_nodes": None,
                  "skipped_nodes": None}
try:
    root = ET.parse(junit).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    counts = {k: int(suite.get(k, "0")) for k in counts}
    element_counts = {
        "testcases": len(root.findall(".//testcase")),
        "failure_nodes": len(root.findall(".//failure")),
        "error_nodes": len(root.findall(".//error")),
        "skipped_nodes": len(root.findall(".//skipped")),
    }
except (ET.ParseError, OSError, AttributeError, TypeError, ValueError) as exc:
    metrics["notes"].append(f"junit unreadable: {exc}")
finally:
    shutil.rmtree(correctness_dir, ignore_errors=True)
metrics["checks"]["correctness"] = {
    "rc": rc, "expected_tests": expected_tests, **counts, **element_counts,
    "tail": output[-3000:],
    "trusted_for_reward": False,
    "role": "diagnostic only; submitted Python shares the pytest interpreter",
}
ok = (rc == 0 and counts["tests"] == expected_tests
      and element_counts["testcases"] == expected_tests
      and counts["failures"] == 0 and counts["errors"] == 0 and counts["skipped"] == 0
      and element_counts["failure_nodes"] == 0 and element_counts["error_nodes"] == 0
      and element_counts["skipped_nodes"] == 0)
if not ok:
    metrics["notes"].append(
        "diagnostic pytest suite did not pass; authoritative correctness is the "
        "root-owned typed black-box oracle below"
    )

# Public helper semantics that do not arise from the nonnegative production
# generator are exercised in a separate candidate process with a secret-shifted
# input.  This preserves the documented "keep existing tests passing" contract
# without trusting candidate-process-owned pytest/JUnit output.
public_api_probe = run_public_api_probe(workdir)
metrics["checks"]["public_api_black_box"] = public_api_probe
if public_api_probe["measurement_validity"] == "external_infra_invalid":
    finish(0, "external_infra_invalid")
if public_api_probe["rc"] == RC_VERIFIER_BUDGET:
    finish(0, "verifier_budget_exhausted")
if public_api_probe["guard_failure"] is not None:
    finish(0, public_api_probe["guard_failure"])
if (
    not public_api_probe["task_started"]
    or public_api_probe["rc"] != 0
    or not public_api_probe["matches"]
):
    finish(0, "public_api_semantics")

# ---------------------------------------------------------------- 2b. deterministic semantic sentinel
require_verifier_budget("semantic sentinel construction", 20.0)
try:
    sentinel_db, sentinel_meta = _build_semantic_sentinel(workdir)
    _assert_semantic_sentinel_fixture(sentinel_db, sentinel_meta)
except Exception as exc:
    metrics["notes"].append(
        f"semantic sentinel construction failed: {type(exc).__name__}: {str(exc)[:500]}"
    )
    finish(0, "verifier_selfcheck_failed")
sentinel_check = {"fixture": sentinel_meta, "runs": []}
metrics["checks"]["semantic_sentinel"] = sentinel_check
for sentinel_month in sentinel_meta["months"]:
    require_verifier_budget(f"semantic sentinel {sentinel_month}", 10.0)
    sentinel_expected = oracle.compute(sentinel_db, sentinel_month)
    try:
        _assert_semantic_sentinel_landmarks(
            sentinel_expected, sentinel_meta, sentinel_month
        )
    except Exception as exc:
        metrics["notes"].append(
            f"semantic sentinel selfcheck failed for {sentinel_month}: "
            f"{type(exc).__name__}: {str(exc)[:500]}"
        )
        finish(0, "verifier_selfcheck_failed")
    month_record = {"month": sentinel_month}
    sentinel_check["runs"].append(month_record)

    local_job, local_output = run_local_semantics_job(
        sentinel_db, sentinel_month, workdir
    )
    local_matches = check_output(local_job, local_output, sentinel_expected)
    del local_output
    month_record["local_path"] = local_job
    if local_job["measurement_validity"] == "external_infra_invalid":
        metrics["notes"].append(
            f"semantic local runner failed before task receipt: {local_job.get('error')}"
        )
        finish(0, "external_infra_invalid")
    if local_job["measurement_validity"] == "indeterminate_integrity":
        finish(0, "indeterminate_integrity")
    if not local_job["input_db_unchanged"]:
        finish(0, "database_mutation")
    if local_job.get("guard_failure") is not None:
        finish(0, local_job["guard_failure"])
    if not local_job["ok"] or not local_matches:
        finish(0, "semantic_sentinel")

    service_job, service_output = run_job(
        APP,
        sentinel_db,
        "n",
        sentinel_month,
        workdir,
        f"semantic-service-{sentinel_month}",
    )
    service_matches = check_output(service_job, service_output, sentinel_expected)
    del service_output
    month_record["service_path"] = service_job
    if service_job["measurement_validity"] == "external_infra_invalid":
        metrics["notes"].append(
            f"semantic service failed before task receipt: {service_job.get('meter_error')}"
        )
        finish(0, "external_infra_invalid")
    if service_job["measurement_validity"] == "indeterminate_integrity":
        finish(0, "indeterminate_integrity")
    if not service_job["input_db_unchanged"]:
        finish(0, "database_mutation")
    if service_job.get("guard_failure") is not None:
        finish(0, service_job["guard_failure"])
    if service_job["queries"] == 0:
        finish(0, "uncounted_queries")
    if not service_job["ok"] or not service_matches:
        finish(0, "semantic_sentinel")
try:
    os.unlink(sentinel_db)
except OSError as exc:
    metrics["notes"].append(
        f"semantic sentinel cleanup failed: {type(exc).__name__}: {exc}"
    )
    finish(0, "verifier_error")

# ---------------------------------------------------------------- 3 + 4 + 5 + 6. hidden workloads
gen = os.path.join(PRISTINE_WORKLOADS, "gen_data.py")
for tag, hidden_config in HIDDEN.items():
    customers = hidden_config["customers"]
    cases = hidden_config["cases"]
    entry = {"customers": customers, "runs": []}
    metrics["hidden"][tag] = entry
    for case_index, case in enumerate(cases):
        require_verifier_budget(f"hidden fixture {tag}/{case_index}", 20.0)
        seed = case["seed"]
        month = case["month"]
        source_db = os.path.join(workdir, f"source-{uuid.uuid4().hex}.db")
        rc, output, _, _, _ = run(
            [sys.executable, "-I", gen, "--out", source_db, "--seed", str(seed),
             "--customers", str(customers), "--month", month] + _SHAPE,
            timeout=300,
            cwd=workdir,
        )
        if rc == RC_VERIFIER_BUDGET:
            metrics["notes"].append(
                f"verifier work deadline exhausted during hidden fixture {tag}/{seed}"
            )
            finish(0, "verifier_budget_exhausted")
        if rc != 0:
            metrics["notes"].append(f"generator failed for {tag}/{seed}: {output[-500:]}")
            finish(0, "verifier_selfcheck_failed")
        generator_counts_before_injection = _table_counts(source_db)
        injected_semantics = None
        if case_index == 0:
            try:
                injected_semantics = _inject_representative_semantic_motifs(
                    source_db, month, seed
                )
            except Exception as exc:
                metrics["notes"].append(
                    f"representative semantic injection failed for {tag}/{seed}: "
                    f"{type(exc).__name__}: {str(exc)[:500]}"
                )
                finish(0, "verifier_selfcheck_failed")
            injected_semantics["counts_before_injection"] = (
                generator_counts_before_injection
            )
            injected_semantics["counts_after_injection"] = _table_counts(source_db)
            try:
                _assert_representative_fixture_landmarks(
                    source_db, injected_semantics
                )
            except Exception as exc:
                metrics["notes"].append(
                    f"representative raw-fixture selfcheck failed for {tag}/{seed}: "
                    f"{type(exc).__name__}: {str(exc)[:500]}"
                )
                finish(0, "verifier_selfcheck_failed")
        if PRIVILEGE_ISOLATION:
            os.chown(source_db, 0, 0)
        os.chmod(source_db, 0o600)
        expected = oracle.compute(source_db, month)
        if injected_semantics is not None:
            try:
                _assert_representative_semantic_landmarks(
                    expected, injected_semantics
                )
            except Exception as exc:
                metrics["notes"].append(
                    f"representative semantic selfcheck failed for {tag}/{seed}: "
                    f"{type(exc).__name__}: {str(exc)[:500]}"
                )
                finish(0, "verifier_selfcheck_failed")
        source_hash = sha256(source_db)
        evaluated_counts = _table_counts(source_db)
        target_start, target_end = oracle.month_bounds(month)
        relevant_profile = relevant_work_profile(
            source_db, target_start, target_end
        )
        selective_ceiling = selective_work_ceilings(relevant_profile)
        rec = {"seed": seed, "month": month,
               "generator_counts_before_injection": generator_counts_before_injection,
               "evaluated_counts": evaluated_counts,
               "relevant_work_profile": relevant_profile,
               "generator_stdout_tail": output.strip()[-200:],
               "db_sha256": source_hash,
               "injected_semantics": injected_semantics}
        entry["runs"].append(rec)

        # The first fresh hidden instance also exercises the documented local-file
        # path.  This hard black-box gate replaces trust in candidate-process-owned
        # pytest/JUnit evidence for the local CLI contract.
        if tag == "n" and case_index == 0:
            local_job, local_output = run_local_semantics_job(
                source_db, month, workdir
            )
            local_matches = check_output(local_job, local_output, expected)
            del local_output
            metrics["checks"]["local_path_black_box"] = local_job
            if local_job["measurement_validity"] == "external_infra_invalid":
                metrics["notes"].append(
                    f"local-path runner failed before task receipt: {local_job.get('error')}"
                )
                finish(0, "external_infra_invalid")
            if local_job["measurement_validity"] == "indeterminate_integrity":
                finish(0, "indeterminate_integrity")
            if not local_job["input_db_unchanged"]:
                finish(0, "database_mutation")
            if local_job.get("guard_failure") is not None:
                finish(0, local_job["guard_failure"])
            if not local_job["ok"] or not local_matches:
                finish(0, "local_path_semantics")

        # Alternate A/B and B/A order across the large cases. Outputs live in
        # root-private, per-job directories and are parsed/unlinked before the other
        # role starts. Separate UIDs plus an empty-UID assertion prevent cross-role
        # process persistence. The one small case remains candidate-first.
        if tag == "n" or case_index % 2 == 0:
            order = ("agent", "baseline")
        else:
            order = ("baseline", "agent")
        rec["execution_order"] = list(order)
        parsed = {}
        for role in order:
            require_verifier_budget(f"hidden {tag}/{case_index} {role}", 10.0)
            src = APP if role == "agent" else PRISTINE_SRC
            rec[role], parsed[role] = run_job(src, source_db, tag, month, workdir, role)
            if sha256(source_db) != source_hash:
                metrics["notes"].append(
                    f"source database changed during {role} run at {tag}/{seed}"
                )
                finish(0, "tampered_hidden_db")

        agent_matches = check_output(rec["agent"], parsed["agent"], expected)
        baseline_matches = check_output(rec["baseline"], parsed["baseline"], expected)
        del parsed
        validity = rec["agent"].get("measurement_validity")
        if validity == "external_infra_invalid":
            metrics["notes"].append(
                f"meter failed before task receipt at {tag}/{seed}: {rec['agent'].get('meter_error')}"
            )
            finish(0, "external_infra_invalid")
        if validity == "indeterminate_integrity":
            metrics["notes"].append(
                f"meter evidence was lost after task start at {tag}/{seed}: {rec['agent'].get('meter_error')}"
            )
            finish(0, "indeterminate_integrity")
        guard_failure = rec["agent"].get("guard_failure")
        if not rec["agent"].get("input_db_unchanged"):
            finish(0, "database_mutation")
        if guard_failure in {
            "meter_policy_denial", "process_isolation", "child_output_limit",
            "task_resource_limit", "task_timeout"
        }:
            finish(0, guard_failure)
        if guard_failure is not None:
            metrics["notes"].append(f"unknown counter guard failure: {guard_failure}")
            finish(0, "verifier_error")
        if rec["agent"]["queries"] == 0:
            finish(0, "uncounted_queries")
        if not rec["agent"]["ok"]:
            finish(0, "hidden_workload")
        if not agent_matches:
            finish(0, "hidden_workload")

        try:
            os.unlink(source_db)
        except OSError as exc:
            metrics["notes"].append(f"baseline db cleanup failed at {tag}/{seed}: {type(exc).__name__}: {exc}")
            finish(0, "verifier_error")
        baseline_validity = rec["baseline"].get("measurement_validity")
        if baseline_validity != "valid_model_outcome":
            metrics["notes"].append(
                f"baseline measurement infrastructure failed at {tag}/{seed}: "
                f"{rec['baseline'].get('meter_error') or rec['baseline'].get('error')}"
            )
            finish(
                0,
                (
                    "external_infra_invalid"
                    if baseline_validity == "external_infra_invalid"
                    else "indeterminate_integrity"
                ),
            )
        if (not rec["baseline"]["ok"] or rec["baseline"].get("guard_failure")
                or not baseline_matches):
            metrics["notes"].append(
                f"baseline disagreed with oracle at {tag}/{seed}: "
                f"{rec['baseline'].get('error') or rec['baseline'].get('first_output_difference')}"
            )
            finish(0, "verifier_selfcheck_failed")
        rec["q_bar"] = rec["baseline"]["queries"] / BAR_DIVISOR
        rec["perf_bar_met"] = rec["agent"]["queries"] <= rec["q_bar"]
        agent_vm_steps = rec["agent"].get("vm_steps")
        rec["absolute_transfer_bar"] = {
            "derivation": selective_ceiling["derivation"],
            "row_ceiling": selective_ceiling["rows"],
            "response_byte_ceiling": selective_ceiling["response_bytes"],
            "rows_met": rec["agent"]["rows_delivered"] <= selective_ceiling["rows"],
            "response_bytes_met": (
                rec["agent"]["response_bytes"] <= selective_ceiling["response_bytes"]
            ),
            "vm_step_ceiling": selective_ceiling["vm_steps"],
            "vm_steps_met": (
                type(agent_vm_steps) is int
                and agent_vm_steps <= selective_ceiling["vm_steps"]
            ),
        }
        base_queries = rec["baseline"]["queries"]
        if base_queries <= Q_REF:
            metrics["notes"].append(
                f"baseline query count {base_queries} is not above reference count {Q_REF} at {tag}/{seed}"
            )
            finish(0, "verifier_selfcheck_failed")
        agent_queries = max(rec["agent"]["queries"], 1)
        rec["query_ratio"] = round(base_queries / agent_queries, 4)
        rec["perf_score_raw"] = round(max(0.0, min(
            1.0,
            math.log(base_queries / agent_queries) / math.log(base_queries / Q_REF),
        )), 4)

for tag in HIDDEN:
    entry = metrics["hidden"][tag]
    runs = entry["runs"]
    entry["q_base_median"] = int(statistics.median(r["baseline"]["queries"] for r in runs))
    entry["q_agent_median"] = int(statistics.median(r["agent"]["queries"] for r in runs))
    entry["q_base"] = entry["q_base_median"]  # backward-compatible summary keys
    entry["q_agent"] = entry["q_agent_median"]
    entry["q_agent_max"] = max(r["agent"]["queries"] for r in runs)
    entry["query_ratio_median"] = round(statistics.median(r["query_ratio"] for r in runs), 4)
    entry["paired_perf_scores"] = [r["perf_score_raw"] for r in runs]
    entry["perf_bar_met"] = all(r["perf_bar_met"] for r in runs)
    entry["absolute_transfer_bar_met"] = all(
        r["absolute_transfer_bar"]["rows_met"]
        and r["absolute_transfer_bar"]["response_bytes_met"]
        and r["absolute_transfer_bar"]["vm_steps_met"]
        for r in runs
    )
    entry["t_base_median"] = statistics.median(r["baseline"]["ext_seconds"] for r in runs)
    entry["t_agent_median"] = statistics.median(r["agent"]["ext_seconds"] for r in runs)
    entry["cpu_base_median"] = statistics.median(r["baseline"]["cpu_seconds"] for r in runs)
    entry["cpu_agent_median"] = statistics.median(r["agent"]["cpu_seconds"] for r in runs)

large, small = metrics["hidden"]["8n"], metrics["hidden"]["n"]
raw_score = statistics.median(r["perf_score_raw"] for r in large["runs"])
metrics["perf_score_method"] = "median of normalized log improvement computed on each paired 8n seed"
metrics["perf_score_raw"] = round(raw_score, 4)
metrics["perf_score"] = round(raw_score, 4) if raw_score >= SCORE_FLOOR else 0.0
data_ratio = large["q_base"] / max(small["q_base"], 1)   # how much more work the large db is (baseline statements)
time_ratio = max(large["t_agent_median"], 0.05) / max(small["t_agent_median"], 0.05)
paired_wall_ratios = [
    r["agent"]["ext_seconds"] / max(r["baseline"]["ext_seconds"], 1e-6)
    for r in large["runs"]
]
large_wall_ratio = statistics.median(paired_wall_ratios)
metrics["checks"]["wallclock"] = {
    "clock": "external (verifier perf_counter around the child; cpu = getrusage children)",
    "role": "large-case conservative regression ceiling; not a speedup estimate",
    "large_case_execution_orders": [r["execution_order"] for r in large["runs"]],
    "paired_agent_over_baseline_large": [round(value, 4) for value in paired_wall_ratios],
    "agent_over_baseline_large": round(large_wall_ratio, 4),
    "baseline_over_agent_large": round(large["t_base_median"] / max(large["t_agent_median"], 1e-6), 4),
    "cpu_agent_over_baseline_large": round(large["cpu_agent_median"] / max(large["cpu_base_median"], 1e-6), 4),
    "data_ratio": round(data_ratio, 4),
    "time_ratio": round(time_ratio, 4),
    "scaling_ratio": round(time_ratio / data_ratio, 4),
    "scaling_ratio_diagnostic_only": True,
}
if not (small["perf_bar_met"] and large["perf_bar_met"]):
    finish(0, "perf_bar")
if not (small["absolute_transfer_bar_met"] and large["absolute_transfer_bar_met"]):
    finish(0, "transfer_bar")
if metrics["checks"]["wallclock"]["agent_over_baseline_large"] > WALLCLOCK_RATIO:
    finish(0, "wallclock_regression")

# ---------------------------------------------------------------- 7. irrelevant-history transfer/resource gate
history_check = {
    "measurement": (
        "paired fresh-process exports through a verifier-owned database service; "
        "rows, response bytes, and SQLite VM-step chunks are recorded server-side; "
        "CPU/wall are external diagnostics"
    ),
    "attempts": [],
    "thresholds": {
        "row_delta_each_attempt": (
            f"positive history-minus-base increase <= max({HISTORY_ROW_ABSOLUTE_ALLOWANCE}, "
            f"ceil({HISTORY_ROW_RELATIVE_ALLOWANCE:.2f} * base_rows_delivered))"
        ),
        "response_byte_delta_each_attempt": (
            f"positive history-minus-base increase <= max({HISTORY_RESPONSE_BYTE_ABSOLUTE_ALLOWANCE}, "
            f"ceil({HISTORY_RESPONSE_BYTE_RELATIVE_ALLOWANCE:.2f} * base_response_bytes))"
        ),
        "vm_step_delta_each_attempt": (
            f"positive history-minus-base increase <= max({HISTORY_VM_STEP_ABSOLUTE_ALLOWANCE}, "
            f"ceil({HISTORY_VM_STEP_RELATIVE_ALLOWANCE:.2f} * base_vm_steps))"
        ),
        "absolute_ceiling": (
            "each job <= a target-month-cardinality-derived row, response-byte, and "
            "pinned-SQLite VM-step ceiling"
        ),
        "cpu_gated": False,
        "wall_ratio_gated": False,
        "wall_cv_gated": False,
    },
    "instrumentation_boundary": (
        "separate-UID Unix-socket SQLite service; metrics return on a parent-only control pipe and "
        "are bound to an attempt id plus database digest"
    ),
}
metrics["checks"]["history_transfer"] = history_check
require_verifier_budget("history fixture construction", 30.0)
try:
    history_base, history_twin, history_expected, fixture = _build_history_pair(workdir, gen)
except VerifierBudgetExhausted as exc:
    metrics["notes"].append(str(exc))
    finish(0, "verifier_budget_exhausted")
except Exception as exc:
    metrics["notes"].append(f"history fixture failed: {type(exc).__name__}: {str(exc)[:500]}")
    finish(0, "verifier_selfcheck_failed")
history_check["fixture"] = fixture
history_paths = {"base": history_base, "history": history_twin}
history_hashes = {kind: sha256(path) for kind, path in history_paths.items()}
history_month = fixture["month"]

# A differential-only gate is forgeable when a submission deliberately does more
# work on the clean side.  Bound both sides independently using semantic
# target-month cardinalities rather than the inefficient pristine implementation.
history_start, history_end = oracle.month_bounds(history_month)
base_profile = relevant_work_profile(history_base, history_start, history_end)
history_profile = relevant_work_profile(history_twin, history_start, history_end)
if base_profile != history_profile:
    metrics["notes"].append(
        f"history semantic work profiles differ: base={base_profile}, history={history_profile}"
    )
    finish(0, "verifier_selfcheck_failed")
history_check["selective_absolute_ceiling"] = {
    "profile": base_profile,
    **selective_work_ceilings(base_profile),
}

for attempt_number in range(1, HISTORY_ATTEMPTS + 1):
    # Alternating the pair order reduces cache/order bias.  Both roles use the
    # same non-semantic cwd prefix, and every invocation receives a fresh DB copy.
    order = ("history", "base") if attempt_number % 2 == 1 else ("base", "history")
    attempt = {"attempt": attempt_number, "order": list(order), "jobs": {}}
    history_check["attempts"].append(attempt)
    outputs = {}
    for kind in order:
        require_verifier_budget(
            f"history attempt {attempt_number} {kind}", 10.0
        )
        job, parsed_output = run_job(
            APP, history_paths[kind], "8n", history_month, workdir, "selectivity"
        )
        attempt["jobs"][kind] = job
        outputs[kind] = parsed_output
        output_matches = check_output(job, parsed_output, history_expected)
        validity = job.get("measurement_validity")
        if validity == "external_infra_invalid":
            metrics["notes"].append(
                f"history meter failed before task receipt: {job.get('meter_error')}"
            )
            finish(0, "external_infra_invalid")
        if validity == "indeterminate_integrity":
            metrics["notes"].append(
                f"history meter evidence was lost after task start: {job.get('meter_error')}"
            )
            finish(0, "indeterminate_integrity")
        guard_failure = job.get("guard_failure")
        if not job.get("input_db_unchanged"):
            finish(0, "database_mutation")
        if guard_failure in {
            "meter_policy_denial", "process_isolation", "child_output_limit",
            "task_resource_limit", "task_timeout"
        }:
            finish(0, guard_failure)
        if guard_failure is not None:
            metrics["notes"].append(
                f"unknown counter guard failure in history gate: {guard_failure}"
            )
            finish(0, "verifier_error")
        if job["queries"] == 0:
            finish(0, "uncounted_queries")
        if not job["ok"] or not output_matches:
            metrics["notes"].append(
                f"history {kind} job failed on attempt {attempt_number}: "
                f"{job.get('error') or job.get('first_output_difference')}"
            )
            finish(0, "history_workload")
    attempt["outputs_equal"] = first_json_difference(outputs["base"], outputs["history"]) is None
    del outputs
    if not attempt["outputs_equal"]:
        finish(0, "history_workload")
    base_rows = attempt["jobs"]["base"]["rows_delivered"]
    history_rows = attempt["jobs"]["history"]["rows_delivered"]
    row_allowance = max(
        HISTORY_ROW_ABSOLUTE_ALLOWANCE,
        math.ceil(HISTORY_ROW_RELATIVE_ALLOWANCE * base_rows),
    )
    attempt["row_delta"] = history_rows - base_rows
    attempt["absolute_row_delta"] = abs(attempt["row_delta"])
    attempt["positive_row_increase"] = max(0, attempt["row_delta"])
    attempt["row_allowance"] = row_allowance
    attempt["row_limit_met"] = attempt["positive_row_increase"] <= row_allowance
    base_response_bytes = attempt["jobs"]["base"]["response_bytes"]
    history_response_bytes = attempt["jobs"]["history"]["response_bytes"]
    response_byte_allowance = max(
        HISTORY_RESPONSE_BYTE_ABSOLUTE_ALLOWANCE,
        math.ceil(HISTORY_RESPONSE_BYTE_RELATIVE_ALLOWANCE * base_response_bytes),
    )
    attempt["response_byte_delta"] = history_response_bytes - base_response_bytes
    attempt["absolute_response_byte_delta"] = abs(attempt["response_byte_delta"])
    attempt["positive_response_byte_increase"] = max(
        0, attempt["response_byte_delta"]
    )
    attempt["response_byte_allowance"] = response_byte_allowance
    attempt["response_byte_limit_met"] = (
        attempt["positive_response_byte_increase"] <= response_byte_allowance
    )
    base_vm_steps = attempt["jobs"]["base"]["vm_steps"]
    history_vm_steps = attempt["jobs"]["history"]["vm_steps"]
    vm_step_allowance = max(
        HISTORY_VM_STEP_ABSOLUTE_ALLOWANCE,
        math.ceil(HISTORY_VM_STEP_RELATIVE_ALLOWANCE * base_vm_steps),
    )
    attempt["vm_step_delta"] = history_vm_steps - base_vm_steps
    attempt["absolute_vm_step_delta"] = abs(attempt["vm_step_delta"])
    attempt["positive_vm_step_increase"] = max(0, attempt["vm_step_delta"])
    attempt["vm_step_allowance"] = vm_step_allowance
    attempt["vm_step_limit_met"] = (
        attempt["positive_vm_step_increase"] <= vm_step_allowance
    )
    attempt["absolute_ceiling_met"] = all(
        job["rows_delivered"] <= history_check["selective_absolute_ceiling"]["rows"]
        and job["response_bytes"] <= history_check["selective_absolute_ceiling"]["response_bytes"]
        and job["vm_steps"] <= history_check["selective_absolute_ceiling"]["vm_steps"]
        for job in attempt["jobs"].values()
    )

if any(sha256(path) != history_hashes[kind] for kind, path in history_paths.items()):
    metrics["notes"].append("history source database changed during isolated job runs")
    finish(0, "tampered_hidden_db")

base_jobs = [attempt["jobs"]["base"] for attempt in history_check["attempts"]]
history_jobs = [attempt["jobs"]["history"] for attempt in history_check["attempts"]]
base_cpu_median = statistics.median(job["cpu_seconds"] for job in base_jobs)
history_cpu_median = statistics.median(job["cpu_seconds"] for job in history_jobs)
cpu_history_over_base = (
    history_cpu_median / base_cpu_median if base_cpu_median > 0 else None
)
cpu_symmetric_ratio = (
    max(cpu_history_over_base, 1.0 / cpu_history_over_base)
    if cpu_history_over_base and cpu_history_over_base > 0
    else None
)
base_wall = [job["ext_seconds"] for job in base_jobs]
history_wall = [job["ext_seconds"] for job in history_jobs]
base_wall_median = statistics.median(base_wall)
history_wall_median = statistics.median(history_wall)
wall_ratio = history_wall_median / max(base_wall_median, 1e-9)
history_check["summary"] = {
    "attempts": HISTORY_ATTEMPTS,
    "all_outputs_equal_oracle_and_pair": all(
        attempt["outputs_equal"]
        and attempt["jobs"]["base"]["output_matches_oracle"]
        and attempt["jobs"]["history"]["output_matches_oracle"]
        for attempt in history_check["attempts"]
    ),
    "all_row_limits_met": all(attempt["row_limit_met"] for attempt in history_check["attempts"]),
    "all_response_byte_limits_met": all(
        attempt["response_byte_limit_met"] for attempt in history_check["attempts"]
    ),
    "all_vm_step_limits_met": all(
        attempt["vm_step_limit_met"] for attempt in history_check["attempts"]
    ),
    "all_absolute_ceilings_met": all(
        attempt["absolute_ceiling_met"] for attempt in history_check["attempts"]
    ),
    "base_external_export_child_cpu_seconds_median": round(base_cpu_median, 6),
    "history_external_export_child_cpu_seconds_median": round(history_cpu_median, 6),
    "external_export_child_cpu_history_over_base": (
        round(cpu_history_over_base, 4) if cpu_history_over_base is not None else None
    ),
    "external_export_child_cpu_symmetric_ratio": (
        round(cpu_symmetric_ratio, 4) if cpu_symmetric_ratio is not None else None
    ),
    "cpu_diagnostic_only": True,
    "base_external_wall_seconds_median": round(base_wall_median, 4),
    "history_external_wall_seconds_median": round(history_wall_median, 4),
    "external_wall_median_ratio": round(wall_ratio, 4),
    "base_external_wall_cv": round(_coefficient_of_variation(base_wall), 4),
    "history_external_wall_cv": round(_coefficient_of_variation(history_wall), 4),
    "wall_diagnostic_only": True,
}
for path in history_paths.values():
    try:
        os.unlink(path)
    except OSError as exc:
        metrics["notes"].append(f"history db cleanup failed: {type(exc).__name__}: {exc}")
        finish(0, "verifier_error")

if not history_check["summary"]["all_row_limits_met"]:
    finish(0, "history_transfer")
if not history_check["summary"]["all_response_byte_limits_met"]:
    finish(0, "history_transfer_bytes")
if not history_check["summary"]["all_vm_step_limits_met"]:
    finish(0, "history_database_work")
if not history_check["summary"]["all_absolute_ceilings_met"]:
    finish(0, "history_absolute_work")
finish(1, None)
