import hashlib
import json
import os
import tempfile
import zipfile


def run(case, size, seed):
    import fsspec

    def norm(value):
        if isinstance(value, dict):
            if 'name' in value:
                return {k: value[k] for k in ('name', 'size', 'type') if k in value}
            return {k: norm(v) for k, v in value.items()}
        if isinstance(value, list):
            return [norm(v) for v in value]
        return value

    def call(func, *args, **kwargs):
        try:
            value = func(*args, **kwargs)
            out = {'ok': norm(value)}
            if isinstance(value, dict):
                out['order'] = list(value)
            return out
        except Exception as exc:
            return {'err': type(exc).__name__}

    with tempfile.TemporaryDirectory(prefix='aqzip-') as tmp:
        def create(name, members, dirs=()):
            path = os.path.join(tmp, name)
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
                for directory in dirs:
                    archive.writestr(directory, b'')
                for member, payload in members:
                    archive.writestr(member, payload)
            return path

        out = {}
        if case == 'bundle':
            members = []
            for i in range(size):
                y = 2023 + i // 672
                month = i // 56 % 12 + 1
                day = i // 2 % 28 + 1
                part = i % 2
                members.append((f'dataset/year={y}/month={month:02d}/day={day:02d}/part-{part:04d}.parquet', b'P' * ((y + month * 3 + day * 5 + part + seed) % 61 + 8)))
            members += [('dataset/_SUCCESS', b''), ('dataset/_metadata', b'meta' * 10)]
            path = create('bundle.zip', members)
            before = hashlib.sha256(open(path, 'rb').read()).hexdigest()
            fs = fsspec.filesystem('zip', fo=path)
            try:
                out['find_all'] = call(fs.find, '')
                out['find_2024'] = call(fs.find, 'dataset/year=2024')
                out['find_dirs'] = call(fs.find, 'dataset', withdirs=True)
                out['glob'] = call(fs.glob, 'dataset/year=2024/month=0*/day=*/*.parquet')
                out['du'] = call(fs.du, 'dataset', total=False)
                out['find_d2'] = call(fs.find, 'dataset', maxdepth=2, withdirs=True)
                out['n'] = len(members)
            finally:
                fs.close()
            out['archive_unchanged'] = before == hashlib.sha256(open(path, 'rb').read()).hexdigest()
        elif case == 'edges':
            archives = {
                'empty': create('empty.zip', []),
                'plain': create('plain.zip', [('a/b/f1', b'1'), ('a/bc/f2', b'22'), ('a/b/c/d/f3', b'333'), ('top', b't'), ('a/b/c/f4', b'4444')]),
                'dirs': create('dirs.zip', [('a/b/f1', b'1'), ('x/y/f2', b'22')], ('a/', 'a/b/', 'a/empty/', 'x/', 'x/y/', 'x/y/z/')),
            }
            for name, path in archives.items():
                fs = fsspec.filesystem('zip', fo=path)
                try:
                    for query in ['', '/', 'a', 'a/', '/a', 'zip://a', 'a/b', 'a/bc', 'a/b/f1', 'top', 'nope', 'a/b/c', 'x', 'x/y', 'x/y/z', 'a/empty']:
                        for withdirs in (False, True):
                            for depth in (None, 0, 1, 2, 3):
                                for detail in (False, True):
                                    key = f'{name}|{query}|{withdirs}|{depth}|{detail}'
                                    out[key] = call(fs.find, query, withdirs=withdirs, maxdepth=depth, detail=detail)
                finally:
                    fs.close()
        else:
            raise ValueError(case)
        encoded = json.dumps(out, sort_keys=True, separators=(',', ':')).encode()
        return {'count': len(out), 'sha256': hashlib.sha256(encoded).hexdigest(), 'outputs': out if case == 'bundle' and size <= 2 else None}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', default='bundle')
    parser.add_argument('--size', type=int, default=1344)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
