"""Private verifier publication helpers. No task or model-specific authority."""
import json
import hashlib
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

ROLE_UIDS = (10001, 10002)
def matching_processes(uids):
    found = []
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            fields = dict(line.split(':', 1) for line in path.read_text().splitlines() if ':' in line)
            if int(fields['Uid'].split()[0]) in uids and not fields['State'].strip().startswith('Z'):
                found.append(int(path.parent.name))
        except (OSError, KeyError, ValueError):
            continue
    return found


def quiesce(uids=ROLE_UIDS, seconds=3):
    if sys.platform != 'linux' or os.geteuid() != 0:
        return {'checked': False, 'quiescent': None, 'initial_pids': []}
    initial = matching_processes(uids)
    deadline = time.monotonic() + seconds
    while True:
        pids = matching_processes(uids)
        if not pids:
            return {'checked': True, 'quiescent': True, 'initial_pids': initial}
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if time.monotonic() >= deadline:
            return {'checked': True, 'quiescent': False, 'initial_pids': initial, 'remaining_pids': matching_processes(uids)}
        time.sleep(.02)


def secure_output_dir(output):
    output = Path(output)
    if output == Path('/logs/verifier') and os.geteuid() == 0:
        # Colima host-backed mounts can report mode 0700 yet ignore the guest UID
        # permission boundary. The container-native parent supplies that boundary.
        parent_info = output.parent.lstat()
        if not stat.S_ISDIR(parent_info.st_mode):
            raise ValueError('publication parent must be a real directory')
        os.chown(output.parent, 0, 0)
        output.parent.chmod(0o700)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = output.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('publication directory must not be a symlink or special file')
    if os.geteuid() == 0:
        os.chown(output, 0, 0)
    output.chmod(0o700)


def uid_write_denied(output):
    if sys.platform != 'linux' or os.geteuid() != 0:
        return {'checked': False, 'denied': None}
    results = {}
    # Benign write-permission probe; no submitted code and no reward-file access.
    program = "import os,sys; p=sys.argv[1];\ntry:\n f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(f);os.unlink(p);sys.exit(1)\nexcept PermissionError: sys.exit(0)"
    for uid in ROLE_UIDS:
        def demote():
            os.setgroups([])
            os.setgid(uid)
            os.setuid(uid)
        proc = subprocess.run([sys.executable, '-I', '-B', '-c', program, str(Path(output) / f'.permission-probe-{uid}')],
                              preexec_fn=demote, cwd='/', env={'PATH': '/usr/bin:/bin'}, timeout=5, capture_output=True)
        results[str(uid)] = proc.returncode == 0
    return {'checked': True, 'denied': all(results.values()), 'uids': results,
            'directory_mode': oct(stat.S_IMODE(Path(output).stat().st_mode)),
            'parent_mode': oct(stat.S_IMODE(Path(output).parent.stat().st_mode))}




def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def bad(value):
        raise ValueError("nonfinite JSON")
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=bad)
    def finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("nonfinite JSON")
        if isinstance(item, dict):
            for child in item.values(): finite(child)
        if isinstance(item, list):
            for child in item: finite(child)
    finite(value)
    return value

def normalize(result):
    result = dict(result)
    eligible = (result.get("score_eligible") is True and result.get("validity") == "valid"
                and result.get("policy_status") == "frozen"
                and result.get("isolation") == "linux_uid_separated"
                and type(result.get("reward")) is int and result["reward"] in (0,1))
    result["score_eligible"] = eligible
    result["model_score_eligible"] = eligible
    result["model_reward"] = result["reward"] if eligible else None
    result["reward"] = result["reward"] if eligible else 0
    return result

def write_receipt(stage, result):
    stage = Path(stage)
    stage.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not stat.S_ISDIR(stage.lstat().st_mode):
        raise ValueError("private staging must be a real directory")
    stage.chmod(0o700)
    result = normalize(result)
    values = {"metrics.json": json.dumps(result, indent=2, allow_nan=False)+"\n",
              "reward.txt":str(result["reward"])+"\n",
              "reward.json":json.dumps({"reward":result["reward"]})+"\n"}
    for name, value in values.items():
        fd, temporary = tempfile.mkstemp(prefix=".receipt-",dir=stage)
        with os.fdopen(fd,"w") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary,stage/name)
    return result

def excluded(reason, detail=None):
    return dict(schema_version=1, reward=0, model_reward=None, score_eligible=False,
                validity="verifier_invalid", reason=reason, detail=detail,
                policy_status="unknown", isolation="unverified")

def private_read_denied(paths, uid=10001):
    if sys.platform!="linux" or os.geteuid()!=0:
        return {"checked":False,"denied":None}
    program = "import sys;\ntry:\n open(sys.argv[1],'rb').read(1);sys.exit(1)\nexcept PermissionError: sys.exit(0)"
    def demote():
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    results = {}
    for path in paths:
        proc = subprocess.run([sys.executable,"-I","-B","-c",program,str(path)],
            preexec_fn=demote,cwd="/",capture_output=True,timeout=5)
        results[str(path)] = proc.returncode==0
    return {"checked":True,"denied":all(results.values()),"paths":results,"uid":uid}

def prepare(stage, output="/logs/verifier"):
    secure_output_dir(output)
    secure_output_dir(stage)
    for name in ("metrics.json","reward.txt","reward.json","verify.log"):
        path = Path(stage)/name
        if path.is_file() or path.is_symlink(): path.unlink()
    raw=Path(stage)/"raw"
    if raw.is_symlink(): raw.unlink()
    elif raw.exists():
        if not raw.is_dir(): raise ValueError("private raw stage is not a directory")
        shutil.rmtree(raw)
    quiet, permission = quiesce(), uid_write_denied(output)
    if quiet.get("quiescent") is not True or permission.get("denied") is not True:
        raise RuntimeError("publication isolation unavailable")
    write_receipt(output,excluded("verification_in_progress"))

def publish(stage, output="/logs/verifier", verifier_rc=0):
    stage, output = Path(stage), Path(output)
    secure_output_dir(output)
    quiet, permissions = quiesce(), uid_write_denied(output)
    try:
        info = (stage/"metrics.json").lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size>64*1024**2:
            raise ValueError("receipt must be a bounded regular file")
        result = strict_json((stage/"metrics.json").read_text())
        if verifier_rc or not isinstance(result,dict) or not result.get("reason"):
            raise ValueError("verifier failed or receipt missing")
    except (OSError, ValueError, TypeError) as exc:
        result = excluded("verifier_crashed_or_missing_receipt", str(exc))
        result["verifier_exit_code"] = verifier_rc
    try:
        stage_info = stage.lstat()
        stage_private = stat.S_ISDIR(stage_info.st_mode) and stat.S_IMODE(stage_info.st_mode)==0o700 and stage_info.st_uid==0
    except OSError:
        stage_private = False
    if quiet.get("quiescent") is not True or permissions.get("denied") is not True or not stage_private:
        result = excluded("publication_integrity_invalid")
        result["validity"] = "indeterminate_integrity"
    artifacts=[]
    try:
        for item in result.get("raw_artifacts",[]):
            relative=Path(item["path"])
            if (len(relative.parts)!=2 or relative.parts[0]!="raw" or relative.name in (".","..")
                or relative.is_absolute()): raise ValueError("invalid raw artifact path")
            path=stage/relative
            info=path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1
                or info.st_size!=item["bytes"] or info.st_size>64*1024**2):
                raise ValueError("invalid raw artifact")
            with path.open("rb") as stream:
                observed=hashlib.file_digest(stream,"sha256").hexdigest()
            if observed!=item["sha256"]: raise ValueError("raw artifact digest mismatch")
            artifacts.append((path,relative))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result=excluded("raw_artifact_integrity_invalid",str(exc))
        artifacts=[]
    # No successful reward is published until all promised raw streams exist.
    write_receipt(output,excluded("publication_in_progress"))
    try:
        if artifacts:
            raw=output/"raw"
            if raw.is_symlink(): raw.unlink()
            elif raw.exists() and not raw.is_dir(): raw.unlink()
            secure_output_dir(raw)
            for source,relative in artifacts:
                target=output/relative
                if target.is_symlink() or target.is_file(): target.unlink()
                if target.exists(): raise ValueError("raw publication destination is not a file")
                fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,"wb") as out,source.open("rb") as incoming:
                    shutil.copyfileobj(incoming,out)
        log=stage/"verify.log"
        if log.is_file() and not log.is_symlink():
            target=output/"verify.log"
            if target.is_symlink() or target.is_file(): target.unlink()
            with target.open("xb") as out,log.open("rb") as incoming:
                shutil.copyfileobj(incoming,out)
            target.chmod(0o600)
    except (OSError,ValueError) as exc:
        result=excluded("raw_publication_failed",str(exc))
    result["publication_boundary"] = dict(quiescence=quiet, uid_write_denial=permissions, stage_private=stage_private)
    result=write_receipt(stage,result)
    write_receipt(output,result)
    return result

class BudgetExceeded(TimeoutError):
    def __init__(self,role):
        self.role=role
        super().__init__(role+" cumulative budget exhausted")

class Budget:
    def __init__(self,limits,clock=time.monotonic):
        self.clock=clock
        self.deadline=clock()+limits["total_wall_seconds"]
        self.maximum={role:limits[role+"_wall_seconds"] for role in ("candidate","baseline")}
        self.spent=dict(candidate=0.0,baseline=0.0)
    def allowance(self,role,per_case):
        left=self.maximum[role]-self.spent[role]
        if left<=0: raise BudgetExceeded(role)
        overall=self.deadline-self.clock()
        if overall<=0: raise BudgetExceeded("verifier")
        role_allowance=min(left,per_case)
        # Do not misattribute exhausted parent overhead to submitted code. A
        # candidate timeout may only consume a candidate/per-case bound, not a
        # silently shortened global-verifier allowance.
        if overall<role_allowance: raise BudgetExceeded("verifier")
        return role_allowance
    def record(self,role,seconds):
        self.spent[role]+=seconds
