"""Check authentic base tests and absence of private benchmark artifacts."""
from pathlib import Path
import hashlib,json
base=Path('/app')
manifest=json.loads(Path('/opt/benchmark-runtime/base-test-hashes.json').read_text())
actual={}
for path in base.rglob('*'):
    rel=path.relative_to(base)
    if path.is_file() and (set(rel.parts)&{'tests','test'} or path.name=='conftest.py' or path.name.startswith('test_') or path.name.endswith('_test.py')):
        actual[str(rel)]=hashlib.sha256(path.read_bytes()).hexdigest()
assert actual==manifest,'upstream tests differ from pinned baseline'
for root in (base,Path('/opt/benchmark-runtime')):
    for path in root.rglob('*'):
        assert not ({'solution','controls','native-upstream','calibration'} & set(path.relative_to(root).parts)),str(path)
        assert path.name not in {'expected.py','policy.json','reference.patch','solve.sh','verify.py'},str(path)
assert not Path('/tests').exists()
assert not list(Path('/tmp').glob('project-metadata.*'))
assert not Path('/tmp/project-source.tar.gz').exists()
assert Path('/app/fsspec/implementations/reference.py').is_file()
print(json.dumps({'agent_surface':'clean','base_test_files':len(actual),'base_test_hashes_match':True,'private_benchmark_assets_present':False,'legitimate_reference_filesystem_retained':True}))
