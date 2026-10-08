"""Parent-owned source snapshots and bounded fresh workers; no oracle imports."""
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time
from boundary import BudgetExceeded, quiesce, strict_json

IGNORED={".git",".venv","venv","__pycache__",".pytest_cache",".afterquery",
         ".assessment",".benchmark-probes",".benchmark-venv","build","dist"}
THREADS={key:"1" for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS","VECLIB_MAXIMUM_THREADS","BLIS_NUM_THREADS")}
CONTEXT_ENV=("PIXI_PROJECT_NAME","PIXI_PROJECT_ROOT","PIXI_PROJECT_MANIFEST",
             "PIXI_ENVIRONMENT_NAME","PIXI_ENVIRONMENT_PLATFORMS","PIXI_IN_SHELL")

class InvalidSource(ValueError): pass

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024**2),b""): h.update(chunk)
    return h.hexdigest()

def snapshot(source,dest,baseline,uid,limits,deadline):
    source,baseline,dest=Path(source),Path(baseline),Path(dest)
    if source.is_symlink() or not source.is_dir():
        raise InvalidSource("source must be a real directory")
    total,manifest=0,{}
    dest.mkdir(mode=0o750)
    for directory,dirs,files in os.walk(source,followlinks=False):
        if time.monotonic()>=deadline: raise BudgetExceeded("verifier")
        dirs[:]=sorted(name for name in dirs if name not in IGNORED)
        for name in dirs:
            if (Path(directory)/name).is_symlink():
                raise InvalidSource("source directory symlink")
        for name in sorted(files):
            if name in IGNORED or name.endswith((".pyc",".pyo")): continue
            path=Path(directory)/name
            relative=path.relative_to(source)
            if path.is_symlink():
                trusted=baseline/relative
                if not trusted.is_symlink() or os.readlink(path)!=os.readlink(trusted):
                    raise InvalidSource("new or changed source symlink")
                actual,expected=path.resolve(),trusted.resolve()
                if not actual.is_relative_to(source.resolve()) or not expected.is_relative_to(baseline.resolve()):
                    raise InvalidSource("source link leaves repository")
                if not actual.is_file() or not expected.is_file():
                    raise InvalidSource("source link is not a regular file")
                path=actual
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode): raise InvalidSource("source special file")
            total+=info.st_size
            if total>limits["source_max_bytes"] or len(manifest)>=limits["source_max_files"]:
                raise InvalidSource("source exceeds declared snapshot limits")
            target=dest/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|getattr(os,"O_NOFOLLOW",0))
            with os.fdopen(fd,"rb") as incoming, target.open("xb") as output:
                live=os.fstat(incoming.fileno())
                if not stat.S_ISREG(live.st_mode) or live.st_size!=info.st_size:
                    raise InvalidSource("source changed during snapshot")
                remaining=info.st_size
                while remaining:
                    if time.monotonic()>=deadline: raise BudgetExceeded("verifier")
                    chunk=incoming.read(min(remaining,1024**2))
                    if not chunk: raise InvalidSource("source shortened during snapshot")
                    output.write(chunk)
                    remaining-=len(chunk)
                if incoming.read(1): raise InvalidSource("source grew during snapshot")
            os.chown(target,0,uid)
            target.chmod(0o440)
            manifest[str(relative)]=digest(target)
    for directory,_,_ in os.walk(dest):
        os.chown(directory,0,uid)
        Path(directory).chmod(0o550)
    encoded=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
    return {"sha256":hashlib.sha256(encoded).hexdigest(),"files":len(manifest),"bytes":total}

def stage_driver(tools_dir,workload,source,config,destination):
    """The read-only driver set excludes expected.py, policy and all answers."""
    destination.mkdir(mode=0o755)
    for origin,name in ((Path(tools_dir)/"probe_worker.py","probe_worker.py"),
                        (Path(tools_dir)/"generic_meter.py","generic_meter.py"),
                        (Path(workload),"workload.py")):
        shutil.copyfile(origin,destination/name)
        (destination/name).chmod(0o444)
    # Match author calibration's adapter exactly: GenericMeter import is included,
    # but monitoring/counting is disabled. Only file locations differ.
    (destination/"bootstrap.py").write_text(
        "import sys\nsys.path.insert(0,"+repr(str(destination))+")\n"
        "from probe_worker import main\nmain("+repr(str(destination/"workload.py"))+","+
        repr(str(source))+","+repr(config)+",enabled=False)\n")
    (destination/"bootstrap.py").chmod(0o444)
    destination.chmod(0o555)

def run_worker(python,source,driver,row,scratch,role,limits,timeout):
    uid=10001 if role=="candidate" else 10002
    scratch.mkdir(mode=0o711)
    scratch.chmod(0o711)  # Explicit public traversal despite the private entrypoint umask.
    writable=scratch/"writable"
    writable.mkdir(mode=0o700)
    os.chown(writable,uid,uid)
    bootstrap=("import sys,runpy; source=sys.argv.pop(1); driver=sys.argv.pop(1); "
        "sys.path.insert(0,source); sys.argv[0]=driver; "
        "runpy.run_path(driver,run_name='__main__')")
    command=[str(python),"-I","-B","-c",bootstrap,str(source),str(driver/"bootstrap.py"),
        "--case",row["case"],"--size",str(row["size"]),"--seed",str(row["seed"])]
    env={"PATH":"/usr/local/bin:/usr/bin:/bin","HOME":str(writable),"TMPDIR":str(writable),
         "LANG":"C.UTF-8","PYTHONHASHSEED":"0",**THREADS}
    env.update({name:os.environ[name] for name in CONTEXT_ENV if name in os.environ})
    def demote():
        os.umask(0o077)
        if hasattr(os,"sched_getaffinity"):
            os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        cpu=max(1,math.ceil(timeout))
        resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu+1))
        resource.setrlimit(resource.RLIMIT_FSIZE,(limits["max_output_bytes"],limits["max_output_bytes"]))
        resource.setrlimit(resource.RLIMIT_AS,(limits["address_space_bytes"],limits["address_space_bytes"]))
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
        resource.setrlimit(resource.RLIMIT_NPROC,(1,1))
    stdout_path,stderr_path=scratch/"stdout.json",scratch/"stderr.log"
    start=time.monotonic()
    with stdout_path.open("wb") as out,stderr_path.open("wb") as err:
        proc=subprocess.Popen(command,cwd=writable,env=env,stdout=out,stderr=err,
            preexec_fn=demote,start_new_session=True)
        timed_out=False
        while True:
            waited,status,usage=os.wait4(proc.pid,os.WNOHANG)
            if waited: break
            if time.monotonic()-start>=timeout:
                timed_out=True
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                _,status,usage=os.wait4(proc.pid,0)
                break
            time.sleep(.002)
        proc.returncode=os.waitstatus_to_exitcode(status)
    wall=time.monotonic()-start
    residual=False
    try:
        os.killpg(proc.pid,0)
        residual=True
        os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError: pass
    quiet=quiesce((uid,))
    record=dict(role=role,uid=uid,mode="uninstrumented",wall_seconds=wall,
        cpu_seconds=usage.ru_utime+usage.ru_stime,peak_rss_mib=usage.ru_maxrss/1024,
        exit_code=proc.returncode,timeout=timed_out,timeout_seconds_effective=timeout,
        surviving_process=residual or bool(quiet["initial_pids"]),uid_quiescence=quiet,
        stdout_path=str(stdout_path),stderr_path=str(stderr_path),
        stdout_sha256=digest(stdout_path),stderr_sha256=digest(stderr_path),
        parse_error=None)
    actual=None
    try:
        info=stdout_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or info.st_size>limits["max_output_bytes"]:
            raise ValueError("stdout is not a bounded root-owned regular stream")
        envelope=strict_json(stdout_path.read_text())
        if (not isinstance(envelope,dict) or set(envelope)!={"schema_version","result","meter","python"}
            or type(envelope["schema_version"]) is not int or envelope["schema_version"]!=1
            or envelope["meter"] is not None or not isinstance(envelope["result"],dict)
            or not isinstance(envelope["python"],str)):
            raise ValueError("stdout must be the uninstrumented probe-worker envelope")
        actual=envelope["result"]
    except (OSError,UnicodeError,ValueError) as exc:
        record["parse_error"]=str(exc)
    return actual,record

def failure(record):
    if record["uid_quiescence"].get("quiescent") is not True: return "integrity_invalid"
    if record["timeout"]: return "timeout"
    if record["exit_code"]==-signal.SIGKILL: return "indeterminate_termination"
    if record["exit_code"]==-signal.SIGXCPU: return "cpu_limit"
    if record["exit_code"]: return "crash"
    if record["surviving_process"]: return "invalid_submission"
    if record["parse_error"]: return "invalid_output"
    return None
