"""Real SQLiteCache maintenance API, fresh or legacy schema; no network/timers."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile


def run(case, size, seed):
    if case not in {'fresh', 'legacy'} or type(size) is not int or not 8 <= size <= 10000 or type(seed) is not int or not 0 <= seed <= 999:
        raise ValueError('unsupported case, size or seed')
    from requests_cache.backends.sqlite import SQLiteCache
    from requests_cache.models import CachedResponse
    from requests_cache.serializers import pickle_serializer

    def response(index, version, expired, forever=False):
        key = f'r{index:05d}'
        unit = f'{seed}:{key}:{version}|'.encode()
        content = (unit * (4096 // len(unit) + 1))[:4096]
        expiry = None if forever else datetime(2000, 1, 1) if expired else datetime(2100, 1, 1)
        return CachedResponse(content=content, expires=expiry, status_code=200, url=f'https://example.invalid/{key}')

    def observe(cache):
        keys = sorted(cache.responses.keys())
        digest = hashlib.sha256()
        for key in keys:
            item = cache.responses[key]
            digest.update(key.encode() + b'\0' + item.content)
        return {'keys': keys, 'redirects': sorted([key, value] for key, value in cache.redirects.items()),
                'content_sha256': digest.hexdigest()}

    with tempfile.TemporaryDirectory(prefix='requests-cache-sweep-') as temporary:
        path = Path(temporary) / 'cache.sqlite'
        if case == 'legacy':
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE responses (key PRIMARY KEY, value)')
                connection.execute('CREATE TABLE redirects (key PRIMARY KEY, value)')
                connection.executemany('INSERT INTO responses VALUES (?,?)',
                    [(f'r{i:05d}', pickle_serializer.dumps(response(i, 0, i % 5 == 0, i % 7 == 0))) for i in range(size)])
                connection.executemany('INSERT INTO redirects VALUES (?,?)',
                    [(f'alias{i:05d}', f'r{i:05d}') for i in range(size)])
        cache = SQLiteCache(path)
        if case == 'fresh':
            with cache.responses.bulk_commit():
                for i in range(size):
                    cache.responses[f'r{i:05d}'] = response(i, 0, i % 5 == 0, i % 7 == 0)
            with cache.redirects.bulk_commit():
                for i in range(size):
                    cache.redirects[f'alias{i:05d}'] = f'r{i:05d}'
        stages = []
        for step in range(16):
            if step in (3, 7, 11):
                with cache.responses.bulk_commit():
                    for j in range(5):
                        index = (13 * seed + 17 * step + 19 * j) % size
                        cache.responses[f'r{index:05d}'] = response(index, step, j % 2 == 0)
            cache.remove_expired_responses()
            if step in (0, 3, 7, 11, 15):
                stages.append({'sweep': step + 1, **observe(cache)})
        cache.responses.close()
        cache.redirects.close()
        reopened_cache = SQLiteCache(path)
        reopened_cache.remove_expired_responses()
        reopened = observe(reopened_cache)
        reopened_cache.responses.close()
        reopened_cache.redirects.close()
    return {'stages': stages, 'reopened': reopened}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--size', required=True, type=int)
    parser.add_argument('--seed', required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
