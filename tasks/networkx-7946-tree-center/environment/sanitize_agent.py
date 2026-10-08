"""Build-only export: preserve exact base tests; omit installer staging/archive."""
import hashlib
import json
from pathlib import Path
import shutil

source = Path("/app")
destination = Path("/agent-app")
shutil.copytree(source, destination, symlinks=True)


def manifest(root):
    entries = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            entries[str(path.relative_to(root))] = {"symlink": str(path.readlink())}
        elif path.is_file():
            entries[str(path.relative_to(root))] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return entries


original = manifest(source)
assert original == manifest(destination)
assert len(original) == 941
assert "networkx/algorithms/isomorphism/tests/test_tree_isomorphism.py" in original
assert "networkx/algorithms/tests/test_distance_measures.py" in original
print(json.dumps({"exact_base_source_export": True, "base_file_entries": len(original),
                  "upstream_base_tests_preserved": True, "rule": "coordinator06:46",
                  "license_sha256": original["LICENSE.txt"]["sha256"]}, sort_keys=True))
