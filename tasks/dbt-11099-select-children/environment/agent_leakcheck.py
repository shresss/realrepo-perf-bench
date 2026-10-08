"""Ordinary final-image file audit; no adversarial integrity claims."""
import hashlib
import json
import os
from pathlib import Path

manifest = json.loads(Path("/opt/benchmark-runtime/base-file-manifest.json").read_text())
actual = {str(path.relative_to("/app")): hashlib.sha256(path.read_bytes()).hexdigest()
          for path in Path("/app").rglob("*") if path.is_file() and not path.is_symlink()}
assert actual == manifest["files"], "base source/tests missing, changed, or augmented with expert assets"
links = {str(path.relative_to("/app")):os.readlink(path) for path in Path("/app").rglob("*") if path.is_symlink()}
assert links == manifest["symlinks"], "base symlinks missing/changed/added"
assert all((Path("/app")/relative).resolve().is_relative_to(Path("/app")) for relative in links)
bad = [str(path) for root in (Path("/opt"), Path("/tmp"), Path("/home/agent"))
       for path in root.rglob("*") if path.name in {
           "expected.py", "policy.json", "reference.patch", "solve.sh", "native.py",
           "native-upstream", "controls", "solution", "project-source.tar.gz", "pristine"}]
assert not bad, bad
assert not Path("/tests").exists()
assert Path("/app/core/dbt/graph/graph.py").is_file()
assert Path("/app/License.md").is_file()
print(json.dumps({"kind":"agent_final_file_visibility_audit", "base_files_exact":True,
    "base_files_count":len(actual), "base_symlinks_exact":True,"base_symlinks_count":len(links),
    "base_tests_count":sum(path.startswith("tests/") for path in actual),
    "base_archive_sha256":manifest["archive_sha256"], "forbidden":bad,
    "limit":"visibility, not arbitrary-code tamper immunity"},sort_keys=True))
