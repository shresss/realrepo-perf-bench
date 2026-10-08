"""Strict admission policy. This module supplies no scoring threshold defaults."""
import hashlib
import json
import math
from pathlib import Path
import re
from boundary import strict_json
from execute import digest

BOUNDARY="whole_fresh_uninstrumented_probe_worker_process_v1"
TASK_FILES=("workload.py","expected.py","cases.json","meter.json")
TOOL_FILES=("probe_worker.py","generic_meter.py")
RUNTIME_FILES=("verify.py","policy.py","execute.py","boundary.py","publish.py","native.py")

class PolicyError(ValueError): pass

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def number(value,name,positive=True):
    if type(value) not in (int,float) or not math.isfinite(value) or (positive and value<=0):
        raise PolicyError(name+" must be a finite positive number")
    return value

def sha(value):
    if not isinstance(value,str) or not re.fullmatch("[0-9a-f]{64}",value):
        raise PolicyError("expected lowercase SHA-256")
    return value

def cases_at(path):
    rows=strict_json(Path(path).read_text())
    if not isinstance(rows,list) or not rows: raise PolicyError("empty cases")
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"id","case","size","seed","role","public"}:
            raise PolicyError("case schema mismatch")
        if not isinstance(row["id"],str) or not row["id"] or row["id"] in seen:
            raise PolicyError("duplicate or missing case identity")
        seen.add(row["id"])
        if not isinstance(row["case"],str) or not row["case"] or type(row["size"]) is not int or row["size"]<0:
            raise PolicyError("bad case input")
        if type(row["seed"]) is not int or type(row["public"]) is not bool or row["role"] not in ("semantic","performance"):
            raise PolicyError("bad case metadata")
    if not any(r["role"]=="performance" for r in rows): raise PolicyError("missing performance cases")
    return rows

def validate(policy,cases):
    if policy.get("schema_version")!=1 or type(policy.get("schema_version")) is not int:
        raise PolicyError("unsupported policy schema")
    if policy.get("status")!="frozen": raise PolicyError("policy is not frozen")
    if policy.get("measurement_boundary")!=BOUNDARY: raise PolicyError("calibration boundary mismatch")
    if not isinstance(policy.get("task_id"),str) or not policy["task_id"]:
        raise PolicyError("task identity missing")
    if type(policy.get("repeats")) is not int or policy["repeats"]<3:
        raise PolicyError("frozen policy requires at least three repeats")
    sha(policy["baseline_sha256"])
    hashes=policy["hashes"]
    for group,names in (("task",TASK_FILES),("tools",TOOL_FILES),("runtime",RUNTIME_FILES)):
        if set(hashes[group])!=set(names): raise PolicyError("exact file hash set required: "+group)
        for value in hashes[group].values(): sha(value)
    limits=policy["limits"]
    for key in ("total_wall_seconds","candidate_wall_seconds","baseline_wall_seconds","parent_reserve_seconds",
                "semantic_case_wall_seconds","performance_case_wall_seconds","native_wall_seconds",
                "source_max_bytes","source_max_files","max_output_bytes","address_space_bytes"):
        number(limits[key],key)
    for key in ("source_max_bytes","source_max_files","max_output_bytes","address_space_bytes"):
        if type(limits[key]) is not int: raise PolicyError("byte/file limits must be integers")
    if limits["candidate_wall_seconds"]+limits["baseline_wall_seconds"]+limits["parent_reserve_seconds"]>limits["total_wall_seconds"]:
        raise PolicyError("role budgets plus parent reserve exceed total")
    performance={row["id"] for row in cases if row["role"]=="performance"}
    gates=policy["cpu_gates"]
    if not isinstance(gates,dict) or not gates or not set(gates).issubset(performance):
        raise PolicyError("CPU gates must address declared performance case IDs")
    for gate in gates.values():
        if set(gate)!={"maximum_candidate_baseline_ratio","baseline_min_seconds","baseline_max_seconds"}:
            raise PolicyError("unknown or missing CPU gate")
        ratio=number(gate["maximum_candidate_baseline_ratio"],"CPU ratio")
        if ratio>=1: raise PolicyError("at least a strict actual speed improvement is required")
        lower=number(gate["baseline_min_seconds"],"baseline floor")
        upper=number(gate["baseline_max_seconds"],"baseline ceiling")
        if lower>=upper: raise PolicyError("empty baseline self-check interval")
    controls=policy["control_provenance"]
    if not isinstance(controls,list) or len(controls)!=4 or {x.get("role") for x in controls}!={"baseline","reference","naive","alternative"}:
        raise PolicyError("baseline/reference/naive/alternative provenance required")
    for entry in controls:
        sha(entry["sha256"])
        relative=Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts: raise PolicyError("control paths must stay inside protected policy directory")
        if entry.get("measurement_boundary")!=BOUNDARY or entry.get("reviewed") is not True:
            raise PolicyError("control provenance is not reviewed for this boundary")
    native=policy["native_regression"]
    if native.get("mode")!="protected_upstream": raise PolicyError("candidate-specific native regression admission is pending")
    sha(native["selection_sha256"])
    if type(native.get("expected_count")) is not int or native["expected_count"]<=0:
        raise PolicyError("native selected-test count must be explicit")
    return policy

def verify_files(policy,task,tools,runtime,policy_dir):
    for group,root in (("task",task),("tools",tools),("runtime",runtime)):
        for name,expected in policy["hashes"][group].items():
            path=Path(root)/name
            if path.is_symlink() or not path.is_file() or digest(path)!=expected:
                raise PolicyError("protected input digest mismatch: "+group+"/"+name)
    for record in policy["control_provenance"]:
        path=Path(policy_dir)/record["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(Path(policy_dir).resolve()) or digest(path)!=record["sha256"]:
            raise PolicyError("protected calibration provenance mismatch")

def exact(actual,expected):
    if type(actual) is not type(expected): return False
    if isinstance(expected,dict):
        return actual.keys()==expected.keys() and all(exact(actual[key],value) for key,value in expected.items())
    if isinstance(expected,list):
        return len(actual)==len(expected) and all(exact(a,e) for a,e in zip(actual,expected))
    return actual==expected

def performance_result(samples,gates):
    """Only parent-observed uninstrumented CPU enters the gate."""
    import statistics
    report={}
    for case_id,gate in gates.items():
        pairs=samples[case_id]
        baseline=[number(row["baseline"],"observed baseline CPU") for row in pairs]
        candidate=[number(row["candidate"],"observed candidate CPU") for row in pairs]
        baseline_median=statistics.median(baseline)
        ratios=[a/b for a,b in zip(candidate,baseline)]
        ratio=statistics.median(ratios)
        report[case_id]=dict(baseline_cpu_seconds=baseline,candidate_cpu_seconds=candidate,
            baseline_median=baseline_median,paired_cpu_ratios=ratios,median_paired_cpu_ratio=ratio,
            maximum_candidate_baseline_ratio=gate["maximum_candidate_baseline_ratio"],
            baseline_self_check_passed=gate["baseline_min_seconds"]<=baseline_median<=gate["baseline_max_seconds"],
            passed=ratio<=gate["maximum_candidate_baseline_ratio"])
    valid=all(row["baseline_self_check_passed"] for row in report.values())
    return valid,valid and all(row["passed"] for row in report.values()),report
