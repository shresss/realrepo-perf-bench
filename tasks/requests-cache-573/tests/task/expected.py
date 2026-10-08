"""Independent stdlib-only cache state model; no candidate or workload imports."""
import hashlib


def expected(case, size, seed):
    if case not in {'fresh', 'legacy'} or type(size) is not int or not 8 <= size <= 10000 or type(seed) is not int or not 0 <= seed <= 999:
        raise ValueError('unsupported case, size or seed')
    records = {f'r{i:05d}': (0, i % 5 == 0 and i % 7 != 0) for i in range(size)}
    aliases = {f'alias{i:05d}': f'r{i:05d}' for i in range(size)}
    stages = []

    def observe():
        digest = hashlib.sha256()
        for key in sorted(records):
            version = records[key][0]
            prefix = f'{seed}:{key}:{version}|'.encode()
            body = (prefix * (4096 // len(prefix) + 1))[:4096]
            digest.update(key.encode() + b'\0' + body)
        return {'keys': sorted(records), 'redirects': sorted([key, value] for key, value in aliases.items()),
                'content_sha256': digest.hexdigest()}

    for step in range(16):
        if step in (3, 7, 11):
            for j in range(5):
                i = (seed * 13 + step * 17 + j * 19) % size
                records[f'r{i:05d}'] = (step, j % 2 == 0)
        records = {key: value for key, value in records.items() if not value[1]}
        aliases = {key: value for key, value in aliases.items() if value in records}
        if step in (0, 3, 7, 11, 15):
            stages.append({'sweep': step + 1, **observe()})
    return {'stages': stages, 'reopened': observe()}
