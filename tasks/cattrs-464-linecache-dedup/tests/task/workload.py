"""Public whole-API configuration conversion workload."""
import hashlib
import json
from pathlib import Path
import random
import sys


def _imports():
    # Runtime puts the immutable snapshot root first; cattrs uses src/ layout.
    roots = [Path(p) for p in sys.path if p] + [Path.cwd()]
    for root in roots:
        if (root / 'src/cattrs').is_dir():
            sys.path.insert(0, str(root / 'src'))
            break
    from attrs import define, field
    from cattrs import Converter
    return define, field, Converter


def run(case: str, size: int, seed: int) -> dict:
    define, field, Converter = _imports()
    if case == 'roundtrip':
        @define
        class TestConfig:
            port: int
            name: str
            labels: list[int]
        rng = random.Random(seed)
        rows = [{'port': rng.randrange(1, 65536), 'name': f'service-{i % 37}',
                 'labels': [i % 7, i % 13, i % 29]} for i in range(size)]
        digest = hashlib.sha256()
        same = True
        for data in rows:
            before = json.dumps(data, sort_keys=True, separators=(',', ':'))
            conv = Converter()
            obj = conv.structure(data, TestConfig)
            got = conv.unstructure(obj)
            same = same and got == data and json.dumps(data, sort_keys=True, separators=(',', ':')) == before
            digest.update(json.dumps(got, sort_keys=True, separators=(',', ':')).encode())
        return {'count': size, 'digest': digest.hexdigest(), 'equal': same}
    if case == 'defaults':
        @define
        class Config:
            value: int = 7
            labels: list[str] = field(factory=list)
        c = Converter()
        outputs = [c.unstructure(c.structure(row, Config)) for row in [{}, {'value': '3'}, {'labels': ['x', 'y']}]]
        return {'outputs': outputs}
    if case == 'override-traceback':
        import linecache
        from cattrs.gen import make_dict_structure_fn, make_dict_unstructure_fn, override
        @define
        class Config:
            value: int
            name: str
        c = Converter(detailed_validation=False)
        outputs = []
        for key in ('value', 'renamed', 'other'):
            sf = make_dict_structure_fn(Config, c, _cattrs_detailed_validation=False, value=override(rename=key))
            uf = make_dict_unstructure_fn(Config, c, value=override(rename=key))
            c.register_structure_hook(Config, sf)
            c.register_unstructure_hook(Config, uf)
            obj = c.structure({key: str(seed % 97), 'name': 'config'}, Config)
            outputs.append((c.unstructure(obj), key, sf, uf))
        result = []
        for data, key, sf, uf in outputs:
            # Check all hooks after distinct source variants are simultaneously live.
            result.append(data)
            result.append({'structure_source': any("['" + key + "']" in line for line in linecache.getlines(sf.__code__.co_filename)),
                           'unstructure_source': any("'" + key + "':" in line for line in linecache.getlines(uf.__code__.co_filename))})
        return {'outputs': result}
    if case == 'typeddict':
        from typing import TypedDict
        class Config(TypedDict):
            value: int
            name: str
        rows = [{'value': str(seed % 101), 'name': 'x'}, {'value': -2, 'name': ''}]
        outputs = []
        for row in rows:
            c = Converter()
            got = c.structure(row, Config)
            outputs.append(c.unstructure(got, Config))
        return {'outputs': outputs, 'input_unchanged': rows[0]['value'] == str(seed % 101)}
    if case == 'validation':
        @define
        class Config:
            value: int
            name: str
        c = Converter(detailed_validation=False)
        errors = []
        for row in ({'value': 'bad', 'name': 'x'}, {'name': 'x'}):
            try:
                c.structure(row, Config)
                errors.append('none')
            except Exception as exc:
                errors.append(type(exc).__name__)
        return {'errors': errors}
    raise ValueError(case)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--case', default='roundtrip')
    p.add_argument('--size', type=int, default=3000)
    p.add_argument('--seed', type=int, default=1729)
    a = p.parse_args()
    print(json.dumps(run(a.case, a.size, a.seed), sort_keys=True))
