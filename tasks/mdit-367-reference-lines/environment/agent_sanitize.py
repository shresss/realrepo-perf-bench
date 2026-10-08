"""Keep pinned base tests; remove unrelated packaging residue, never private assets."""
from pathlib import Path
import shutil

for root in (Path("/app"),):
    for name in ("benchmarking", "scripts", "docs", ".github"):
        path = root / name
        if path.exists():
            shutil.rmtree(path)
for path in Path("/tmp").glob("project-metadata.*"):
    if path.is_dir():
        shutil.rmtree(path)
archive = Path("/tmp/project-source.tar.gz")
if archive.exists():
    archive.unlink()
assert Path("/app/LICENSE").is_file()
assert Path("/app/markdown_it/rules_block/reference.py").is_file()
assert Path("/app/tests/test_port/test_references.py").is_file()
