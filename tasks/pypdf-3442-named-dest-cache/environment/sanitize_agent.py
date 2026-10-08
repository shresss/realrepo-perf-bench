"""Sanitize only fixed, image-build-owned paths; assert final agent privacy."""
import json
import hashlib
from pathlib import Path
import shutil
import sys

if "--check" not in sys.argv:
    archive = Path("/tmp/project-source.tar.gz")
    if archive.exists():
        assert archive.is_file() and not archive.is_symlink()
        archive.unlink()
    for metadata in Path("/tmp").iterdir():
        if metadata.name.startswith("project-metadata."):
            assert metadata.is_dir() and not metadata.is_symlink()
            assert (metadata / "source" / "pypdf").is_dir()
            shutil.rmtree(metadata)

for private in ("solution", "controls", "expected.py", "policy.json", "reference.patch"):
    assert not (Path("/app") / private).exists(), private
for private in ("/tests", "/solution"):
    assert not Path(private).exists(), private
assert not Path("/tmp/project-source.tar.gz").exists()
assert not any(p.name.startswith("project-metadata.") for p in Path("/tmp").iterdir())
manifest = json.loads(Path("/opt/benchmark-runtime/upstream-base-manifest.json").read_text())
actual = {str(p.relative_to("/app")):hashlib.sha256(p.read_bytes()).hexdigest()
          for directory in ("tests", "resources") for p in (Path("/app")/directory).rglob("*") if p.is_file()}
assert actual == manifest["files"], "upstream tests/resources must match BASE, never expert-added/modified bytes"
assert manifest["base_commit"] == "46a2b04d099a7d2f0396e7b212f06e3922c4abc0"
print(json.dumps({"agent_privacy": "PASS", "upstream_tests": True,
                  "upstream_fixture_data": True, "base_assertion_files":len(actual),
                  "source_archive": False, "private_benchmark_assets": False}, sort_keys=True))
