"""Root parent verifier. Run only in an ephemeral, isolated Linux task container."""
import argparse
import errno
import importlib.util
import json
import os
import shutil
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from boundary import (ROLE_UIDS, Budget, BudgetExceeded, excluded, matching_processes, private_read_denied,
                      quiesce, strict_json, write_receipt)
from execute import InvalidSource, digest, failure, run_worker, snapshot, stage_driver
from policy import BOUNDARY, PolicyError, cases_at, exact, performance_result, validate, verify_files


class StopRun(Exception):
    def __init__(self,reason,valid=False,detail=None):
        self.reason,self.valid,self.detail=reason,valid,detail
        super().__init__(reason)


def private_root(path):
    info=Path(path).lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700:
        raise StopRun("protected_root_is_not_native_root_private")


# ---- runtime v1.1: per-worker state hygiene ---------------------------------
# Root-only cleanup between worker invocations, always outside a worker's timed
# window (execute.run_worker and native.run_native are byte-identical to v1).
# Every invocation starts from the state a fresh process on a fresh machine
# would see: no scratch tree of an earlier worker, no worker-owned entries in
# shared scratch directories, and no worker-owned System V IPC objects.
HYGIENE_VERSION="runtime-v1.1-per-worker-state-hygiene"
SHARED_STATE_DIRS=("/tmp","/var/tmp","/dev/shm","/dev/mqueue","/run/lock")
SYSV_IPC=(("shm","shmid","-m"),("msg","msqid","-q"),("sem","semid","-s"))


class HygieneError(OSError): pass


def _remove_at(parent_fd,name):
    """Remove one entry below an open directory without following any symlink.

    Never holds more than three descriptors and never recurses: each nested
    directory is renamed up into the top directory before it is emptied, so
    worker-built trees deeper than the recursion limit, RLIMIT_NOFILE or
    PATH_MAX are still removed. Returns the number of entries removed."""
    info=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode):
        os.unlink(name,dir_fd=parent_fd)
        return 1
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    removed,serial=0,0
    top=os.open(name,flags,dir_fd=parent_fd)
    try:
        while True:
            names=os.listdir(top)
            if not names: break
            taken=set(names)
            for child in names:
                if not stat.S_ISDIR(os.stat(child,dir_fd=top,follow_symlinks=False).st_mode):
                    os.unlink(child,dir_fd=top)
                    removed+=1
                    continue
                inner=os.open(child,flags,dir_fd=top)
                try:
                    for grandchild in os.listdir(inner):
                        if stat.S_ISDIR(os.stat(grandchild,dir_fd=inner,follow_symlinks=False).st_mode):
                            serial+=1
                            while ".hygiene-%d"%serial in taken: serial+=1
                            taken.add(".hygiene-%d"%serial)
                            os.rename(grandchild,".hygiene-%d"%serial,src_dir_fd=inner,dst_dir_fd=top)
                        else:
                            os.unlink(grandchild,dir_fd=inner)
                            removed+=1
                finally: os.close(inner)
                os.rmdir(child,dir_fd=top)
                removed+=1
    finally: os.close(top)
    os.rmdir(name,dir_fd=parent_fd)
    return removed+1


def remove_tree(path):
    """Remove path (file, symlink or directory tree) as root; 0 if already absent."""
    path=Path(path)
    parent_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:
        try: return _remove_at(parent_fd,path.name)
        except FileNotFoundError: return 0
    finally: os.close(parent_fd)


def worker_reachable(info):
    """True when a worker UID (gid==uid, no supplementary groups) can traverse it."""
    if info.st_uid in ROLE_UIDS: return True
    bit=stat.S_IXGRP if info.st_gid in ROLE_UIDS else stat.S_IXOTH
    return bool(info.st_mode & bit)


def sweep_shared_dirs(uids=ROLE_UIDS,roots=SHARED_STATE_DIRS,exclude=()):
    """Remove every entry owned by a worker UID below the shared scratch roots.

    A worker-owned entry is removed whole. Root-owned directories that a worker
    can traverse are searched (same filesystem only), because a world-writable
    child could hold worker entries; untraversable ones cannot. Excluded paths
    (the verifier work dir) are never entered. None marks an absent root."""
    excluded={os.path.realpath(path) for path in exclude}
    removed,seen={},set()
    for root in roots:
        real=os.path.realpath(root)
        if not os.path.isdir(real):
            removed[root]=None
            continue
        if real in seen:
            removed[root]=0
            continue
        seen.add(real)
        device=os.lstat(real).st_dev
        count=0
        pending=[real]
        while pending:
            directory=pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    path=entry.path
                    if os.path.realpath(path) in excluded: continue
                    info=entry.stat(follow_symlinks=False)
                    if info.st_uid in uids:
                        count+=remove_tree(path)
                    elif (stat.S_ISDIR(info.st_mode) and info.st_dev==device
                          and worker_reachable(info)):
                        pending.append(path)
        removed[root]=count
    return removed


def sysv_ipc_objects(uids=ROLE_UIDS,proc=Path("/proc/sysvipc")):
    """List System V IPC objects whose owner or creator is a worker UID."""
    found=[]
    if not Path(proc).is_dir(): return None
    for kind,column,_ in SYSV_IPC:
        try: lines=(Path(proc)/kind).read_text().splitlines()
        except FileNotFoundError: continue
        if not lines: continue
        header=lines[0].split()
        for line in lines[1:]:
            fields=dict(zip(header,line.split()))
            if int(fields["uid"]) in uids or int(fields["cuid"]) in uids:
                found.append((kind,int(fields[column])))
    return found


def sysv_ipc_owners(objects,proc=Path("/proc/sysvipc")):
    """(kind, id, uid, cuid) rows for the listed objects."""
    wanted,rows=set(objects),[]
    for kind,column,_ in SYSV_IPC:
        try: lines=(Path(proc)/kind).read_text().splitlines()
        except FileNotFoundError: continue
        header=lines[0].split() if lines else []
        for line in lines[1:]:
            fields=dict(zip(header,line.split()))
            if (kind,int(fields[column])) in wanted:
                rows.append((kind,int(fields[column]),int(fields["uid"]),int(fields["cuid"])))
    return rows


IPC_REMOVER=r"""
import ctypes,json,sys
libc=ctypes.CDLL(None,use_errno=True)
calls={"shm":libc.shmctl,"msg":libc.msgctl,"sem":libc.semctl}
for name in ("shm","msg"): calls[name].argtypes=(ctypes.c_int,ctypes.c_int,ctypes.c_void_p)
calls["sem"].argtypes=(ctypes.c_int,ctypes.c_int,ctypes.c_int)
result=[]
for kind,identifier in json.loads(sys.argv[1]):
    code=calls[kind](identifier,0,0) if kind=="sem" else calls[kind](identifier,0,None)
    result.append([kind,identifier,0 if code==0 else ctypes.get_errno()])
print(json.dumps(result))
"""


def _demoted(uid):
    def demote():
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return demote


def remove_sysv_ipc(uid,objects):
    """IPC_RMID as the owning worker UID.

    Container root normally lacks CAP_SYS_ADMIN/CAP_IPC_OWNER, so root cannot
    remove another UID's object; its owner or creator always can. A tiny
    verifier-authored helper runs demoted, outside every timed window. ipcrm
    (also demoted) is the fallback when the libc call is unavailable."""
    removed=[]
    try:
        proc=subprocess.run([sys.executable,"-I","-B","-c",IPC_REMOVER,json.dumps(objects)],preexec_fn=_demoted(uid),
                            cwd="/",env={"PATH":"/usr/bin:/bin"},capture_output=True,text=True,timeout=10)
        rows=json.loads(proc.stdout) if proc.returncode==0 else []
        removed=[(kind,identifier) for kind,identifier,code in rows if code==0]
        absent={(kind,identifier) for kind,identifier,code in rows if code in (errno.EINVAL,errno.EIDRM)}
    except (OSError,ValueError,subprocess.SubprocessError):
        absent=set()
    tool=shutil.which("ipcrm",path="/usr/bin:/bin:/usr/sbin:/sbin")
    flags=dict((name,option) for name,_,option in SYSV_IPC)
    for kind,identifier in objects:
        if (kind,identifier) in removed or (kind,identifier) in absent or not tool: continue
        proc=subprocess.run([tool,flags[kind],str(identifier)],preexec_fn=_demoted(uid),cwd="/",
                            env={"PATH":"/usr/bin:/bin"},capture_output=True,timeout=10)
        if proc.returncode==0: removed.append((kind,identifier))
    return removed


def purge_sysv_ipc(uids=ROLE_UIDS,proc=Path("/proc/sysvipc")):
    """Remove every System V IPC object a worker UID owns or created."""
    objects=sysv_ipc_objects(uids,proc)
    if objects is None: return None
    removed={kind:0 for kind,_,_ in SYSV_IPC}
    if objects:
        owners={}
        for kind,identifier,uid,cuid in sysv_ipc_owners(objects,proc):
            owners.setdefault(cuid if cuid in uids else uid,[]).append((kind,identifier))
        for uid,items in sorted(owners.items()):
            for kind,_ in remove_sysv_ipc(uid,items): removed[kind]+=1
    left=sysv_ipc_objects(uids,proc)
    if left: raise HygieneError("SysV IPC objects survived removal: "+repr(left))
    return removed


def observe_state_dirs(candidate):
    """Record (never gate on) the shared directories test.sh hardened."""
    rows={}
    for path in SHARED_STATE_DIRS+(str(candidate),):
        try:
            info=os.lstat(path)
            row=dict(exists=True,symlink=stat.S_ISLNK(info.st_mode),
                     mode=oct(stat.S_IMODE(os.stat(path).st_mode)),uid=os.stat(path).st_uid)
            if path!=str(candidate) and os.path.isdir(path): row["entries"]=len(os.listdir(path))
        except OSError as exc:
            row=dict(exists=False,error=type(exc).__name__)
        rows[path]=row
    return rows


def prepare_invocation(hygiene,work,role,kind):
    """Before a worker launch: no live worker process, no worker-owned state."""
    start=time.monotonic()
    try:
        live=matching_processes(ROLE_UIDS)
        if live: raise HygieneError("worker UID process alive before launch: "+repr(live))
        row=dict(index=len(hygiene["invocations"]),role=role,kind=kind,
                 pre_launch=dict(sysv_ipc_removed=purge_sysv_ipc(),
                                 shared_dir_entries_removed=sweep_shared_dirs(exclude=(work,))))
    except HygieneError: raise
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        raise HygieneError("pre-launch cleanup failed: "+type(exc).__name__+": "+str(exc)) from exc
    row["pre_launch"]["seconds"]=time.monotonic()-start
    hygiene["invocations"].append(row)
    return row


def finish_invocation(hygiene,row,scratch):
    """After a worker returned and its raw streams were archived: drop its scratch."""
    start=time.monotonic()
    try: removed=remove_tree(scratch)
    except OSError as exc:
        raise HygieneError("scratch removal failed: "+type(exc).__name__+": "+str(exc)) from exc
    row["post_return"]=dict(scratch=str(scratch),scratch_entries_removed=removed)
    row["post_return"]["seconds"]=time.monotonic()-start
    totals=hygiene["totals"]
    totals["invocations"]+=1
    totals["scratch_entries_removed"]+=row["post_return"]["scratch_entries_removed"]
    totals["shared_dir_entries_removed"]+=sum(v or 0 for v in row["pre_launch"]["shared_dir_entries_removed"].values())
    totals["sysv_ipc_removed"]+=sum((row["pre_launch"]["sysv_ipc_removed"] or {}).values())
    totals["seconds"]+=row["pre_launch"]["seconds"]+row["post_return"]["seconds"]


def archive_streams(record,stage,number,maximum,artifacts):
    """Keep root-owned raw evidence in the private stage for later publication."""
    raw=stage/"raw"
    raw.mkdir(mode=0o700,exist_ok=True)
    for field in ("stdout","stderr"):
        value=record.get(field+"_path")
        if not value: continue
        source=Path(value)
        info=source.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1
            or info.st_size>maximum): raise StopRun("raw_stream_integrity_invalid")
        if digest(source)!=record[field+"_sha256"]: raise StopRun("raw_stream_hash_changed")
        relative="raw/%04d-%s.bin"%(number,field)
        target=stage/relative
        with source.open("rb") as incoming,target.open("xb") as outgoing:
            shutil.copyfileobj(incoming,outgoing)
        target.chmod(0o600)
        if digest(target)!=record[field+"_sha256"]: raise StopRun("raw_archive_hash_mismatch")
        artifacts.append(dict(path=relative,sha256=record[field+"_sha256"],bytes=info.st_size))
        record[field+"_path"]=relative


def evaluate(args):
    stage=Path(args.output)
    stage.mkdir(parents=True,exist_ok=True,mode=0o700)
    result=excluded("initializing")
    result.update(measurement_boundary=BOUNDARY,records=[],native_records=[],performance={},raw_artifacts=[],
                  task_id=None,policy_status="unset",score_eligible=False)
    policy=None
    budget=None
    def done(reason,valid=False,reward=0,detail=None):
        result.update(reason=reason,validity="valid" if valid else "verifier_invalid",
                      score_eligible=valid,reward=reward,detail=detail)
        if budget: result["budget_spent_seconds"]=budget.spent
        return write_receipt(stage,result)
    try:
        policy_path=Path(args.policy)
        if not policy_path.is_file(): return done("policy_unset")
        policy=strict_json(policy_path.read_text())
        if not isinstance(policy,dict): raise PolicyError("policy must be an object")
        result["policy_status"]=policy.get("status","unset")
        if policy.get("status")!="frozen": return done("policy_unfrozen")
        task,tools,runtime=Path(args.task),Path(args.tools),Path(__file__).resolve().parent
        cases=cases_at(task/"cases.json")
        validate(policy,cases)
        verify_files(policy,task,tools,runtime,policy_path.parent)
        result.update(task_id=policy["task_id"],policy_sha256=digest(policy_path),hashes=policy["hashes"],
                      control_provenance=policy["control_provenance"])
        if sys.platform!="linux" or os.geteuid()!=0:
            return done("requires_ephemeral_root_linux_container")
        private_root(args.private_root)
        protected=[task,tools,runtime,Path(args.baseline),Path(args.native_upstream),policy_path,stage]
        private=Path(args.private_root).resolve()
        if not all(path.resolve().is_relative_to(private) for path in protected):
            raise StopRun("all_trusted_inputs_and_stage_must_be_inside_private_root")
        if any(path.is_symlink() for path in protected): raise StopRun("trusted_input_symlink")
        quiet=quiesce()
        if quiet.get("quiescent") is not True: raise StopRun("uid_quiescence_unavailable")
        result["initial_uid_quiescence"]=quiet
        probes={str(uid):private_read_denied([task/"expected.py",policy_path,runtime/"verify.py"],uid) for uid in (10001,10002)}
        result["private_read_denial"]=probes
        if not all(row.get("denied") is True for row in probes.values()):
            raise StopRun("private_input_read_boundary_unavailable")
        result["isolation"]="linux_uid_separated"
        limits=policy["limits"]
        budget=Budget(limits)
        work=Path(tempfile.mkdtemp(prefix="afterquery-runtime-",dir="/tmp"))
        work.chmod(0o711)
        result["worker_artifact_root"]=str(work)
        hygiene=dict(version=HYGIENE_VERSION,environment=observe_state_dirs(args.candidate),invocations=[],
                     totals=dict(invocations=0,scratch_entries_removed=0,shared_dir_entries_removed=0,
                                 sysv_ipc_removed=0,seconds=0.0))
        result["worker_state_hygiene"]=hygiene
        from native import run_native, selection_manifest
        manifest=selection_manifest(Path(args.native_upstream))
        if (manifest["sha256"]!=policy["native_regression"]["selection_sha256"]
            or manifest["expected_count"]!=policy["native_regression"]["expected_count"]):
            raise StopRun("native_selection_policy_mismatch")
        result["native_selection"]=manifest
        roots={role:work/(role+"-source") for role in ("baseline","candidate")}
        result["source_snapshots"]={}
        for role in ("baseline","candidate"):
            origin=args.baseline if role=="baseline" else args.candidate
            try:
                record=snapshot(origin,roots[role],args.baseline,10002 if role=="baseline" else 10001,limits,budget.deadline)
            except InvalidSource as exc:
                raise StopRun(role+"_invalid_source",role=="candidate",str(exc)) from exc
            result["source_snapshots"][role]=record
            if role=="baseline" and record["sha256"]!=policy["baseline_sha256"]:
                raise StopRun("baseline_source_hash_mismatch")
        baseline_file=next(path for path in roots["baseline"].rglob("*") if path.is_file())
        snapshot_denial=private_read_denied([baseline_file],10001)
        result["baseline_snapshot_read_denial"]=snapshot_denial
        if snapshot_denial.get("denied") is not True: raise StopRun("baseline_snapshot_not_private_from_candidate")
        config=strict_json((task/"meter.json").read_text())
        drivers={role:work/(role+"-driver") for role in roots}
        for role in roots: stage_driver(tools,task/"workload.py",roots[role],config,drivers[role])
        # Expected values are computed by the protected parent, before any candidate
        # worker. Candidate stdout and diagnostic counters never certify themselves.
        spec=importlib.util.spec_from_file_location("protected_expected",task/"expected.py")
        oracle=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        expected={}
        for row in cases:
            if time.monotonic()>=budget.deadline: raise BudgetExceeded("verifier")
            value=oracle.expected(row["case"],row["size"],row["seed"])
            expected[row["id"]]=strict_json(json.dumps(value,allow_nan=False))
        def compare(actual,want):
            compared=oracle.equivalent(actual,want) if hasattr(oracle,"equivalent") else exact(actual,want)
            if type(compared) is not bool: raise StopRun("oracle_comparator_did_not_return_bool")
            return compared
        # Native regression is candidate-specific, but not part of CPU speed ratios.
        for role in ("baseline","candidate"):
            invocation=prepare_invocation(hygiene,work,role,"native")
            timeout=budget.allowance(role,limits["native_wall_seconds"])
            native=run_native(args.python,roots[role],Path(args.native_upstream),work/(role+"-native"),role,limits,timeout)
            budget.record(role,native["wall_seconds"])
            result["native_records"].append(native)
            archive_streams(native,stage,len(result["native_records"]),limits["max_output_bytes"],result["raw_artifacts"])
            finish_invocation(hygiene,invocation,work/(role+"-native"))
            if native.get("outcome")!="passed":
                is_candidate_failure=role=="candidate" and native.get("outcome")=="failed"
                raise StopRun(role+"_native_"+native.get("reason","invalid"),is_candidate_failure)
        samples={row["id"]:[] for row in cases if row["role"]=="performance"}
        index=0
        for row in cases:
            count=policy["repeats"] if row["role"]=="performance" else 1
            for repeat in range(count):
                pair={}
                for role in (("baseline","candidate") if repeat%2==0 else ("candidate","baseline")):
                    invocation=prepare_invocation(hygiene,work,role,"worker")
                    scratch=work/("worker-%04d"%index)
                    timeout=budget.allowance(role,limits[row["role"]+"_case_wall_seconds"])
                    actual,record=run_worker(args.python,roots[role],drivers[role],row,scratch,role,limits,timeout)
                    index+=1
                    budget.record(role,record["wall_seconds"])
                    record.update(case_id=row["id"],case=row["case"],size=row["size"],seed=row["seed"],repeat=repeat)
                    result["records"].append(record)
                    archive_streams(record,stage,index+2,limits["max_output_bytes"],result["raw_artifacts"])
                    finish_invocation(hygiene,invocation,scratch)
                    failed=failure(record)
                    if failed:
                        raise StopRun(role+"_"+failed,role=="candidate" and failed not in
                                      ("integrity_invalid","indeterminate_termination"))
                    correct=compare(actual,expected[row["id"]])
                    record["correct"]=correct
                    if not correct: raise StopRun(role+"_semantic_mismatch",role=="candidate")
                    pair[role]=record["cpu_seconds"]
                if row["role"]=="performance": samples[row["id"]].append(pair)
        valid,passed,report=performance_result(samples,policy["cpu_gates"])
        result["performance"]=report
        result["all_scale_cpu_samples_diagnostic"]=samples
        result["gate_scope"]={"case_ids":list(policy["cpu_gates"]),
            "ungated_scales_are_diagnostic_only":True,"small_size_no_regression_claim":False,
            "repeats_are_repeatability_not_independent_tasks":True}
        if not valid: return done("baseline_runtime_self_check_failed")
        return done("accepted" if passed else "performance_not_met",True,int(passed))
    except StopRun as exc:
        return done(exc.reason,exc.valid,detail=exc.detail)
    except HygieneError as exc:
        return done("worker_state_hygiene_failed",detail=str(exc))
    except BudgetExceeded as exc:
        return done(exc.role+"_cumulative_budget_exhausted",exc.role=="candidate")
    except (PolicyError,KeyError,TypeError,ValueError,OSError,ImportError) as exc:
        return done("verifier_configuration_or_execution_invalid",detail=type(exc).__name__+": "+str(exc))


def main():
    parser=argparse.ArgumentParser()
    for name in ("task","baseline","candidate","tools","native-upstream","policy","output"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--python",default=sys.executable)
    parser.add_argument("--private-root",default="/tests")
    args=parser.parse_args()
    result=evaluate(args)
    print(json.dumps({key:result[key] for key in ("reason","validity","score_eligible","model_reward")},allow_nan=False))


if __name__=="__main__": main()
