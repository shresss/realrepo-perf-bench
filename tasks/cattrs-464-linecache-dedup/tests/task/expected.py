"""Independent stdlib oracle: expected conversion semantics, no cattrs imports."""
import hashlib
import json
import random


def expected(case, size, seed):
    if case == 'roundtrip':
        rng = random.Random(seed)
        digest = hashlib.sha256()
        for i in range(size):
            row = {'port': rng.randrange(1, 65536), 'name': 'service-' + str(i % 37),
                   'labels': [i % 7, i % 13, i % 29]}
            digest.update(json.dumps(row, sort_keys=True, separators=(',', ':')).encode())
        return {'count': size, 'digest': digest.hexdigest(), 'equal': True}
    if case == 'defaults':
        return {'outputs': [{'value': 7, 'labels': []}, {'value': 3, 'labels': []}, {'value': 7, 'labels': ['x', 'y']}]}
    if case == 'override-traceback':
        outputs = []
        for key in ('value', 'renamed', 'other'):
            outputs.extend([{key: seed % 97, 'name': 'config'}, {'structure_source': True, 'unstructure_source': True}])
        return {'outputs': outputs}
    if case == 'typeddict':
        return {'outputs': [{'value': seed % 101, 'name': 'x'}, {'value': -2, 'name': ''}], 'input_unchanged': True}
    if case == 'validation':
        return {'errors': ['ValueError', 'KeyError']}
    raise ValueError(case)
