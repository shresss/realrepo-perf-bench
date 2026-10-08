"""Ordinary packaged-file visibility check; does not attempt verifier intrusion."""
import hashlib
import json
from pathlib import Path

manifest = json.loads(Path("/opt/benchmark-runtime/base-test-manifest.json").read_text())
allowed_tests = {"/app/" + name for name in manifest["test_files"]}
bad = []
for root in (Path("/app"), Path("/opt"), Path("/tmp"), Path("/home/agent")):
    for path in root.rglob("*"):
        if path.name in {"expected.py", "policy.json", "reference.patch", "public-reference.patch", "solve.sh", "verify.py", "native_driver.py", "commonmark.json", "commonmark_extras.md", "project-source.tar.gz"} and str(path) not in allowed_tests:
            bad.append(str(path))
        if path.is_dir() and path.name in {"solution", "controls", "native-upstream", "pristine"}:
            bad.append(str(path))
assert not bad, bad
assert not Path("/tests").exists()
assert Path("/app/markdown_it/rules_block/reference.py").is_file()
assert Path("/app/LICENSE").is_file()
actual_tests = {str(p.relative_to("/app")): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path("/app/tests").rglob("*") if p.is_file()}
assert actual_tests == manifest["test_files"], "base tests missing, modified, extra, or reference-added"
files = sorted(str(p.relative_to("/app")) for p in Path("/app").rglob("*") if p.is_file())
print(json.dumps({"kind":"agent_packaged_file_leakcheck","forbidden":bad,"app_files":files,
                  "base_tests_count":len(actual_tests), "base_tests_exact":True,
                  "base_archive_sha256":manifest["archive_sha256"],
                  "license_sha256":hashlib.sha256(Path("/app/LICENSE").read_bytes()).hexdigest()},sort_keys=True))
