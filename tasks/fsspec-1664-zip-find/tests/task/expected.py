"""Independent stdlib model of the archive's logical path tree.

Does not load fsspec, zipfile, the candidate, or any recorded golden output.
"""
import fnmatch
import hashlib
import json


def expected(case, size, seed):
    def tree(files, directories=()):
        nodes = {}
        for path in [*files, *directories]:
            segments = path.strip('/').split('/')
            for length in range(1, len(segments)):
                name = '/'.join(segments[:length])
                nodes[name] = {'name': name, 'size': 0, 'type': 'directory'}
        for path in directories:
            name = path.rstrip('/')
            nodes[name] = {'name': name, 'size': 0, 'type': 'directory'}
        for name, length in files.items():
            nodes[name] = {'name': name, 'size': length, 'type': 'file'}
        return nodes

    def find(nodes, query, withdirs=False, depth=None, detail=False):
        if depth is not None and depth < 1:
            return {'err': 'ValueError'}
        query = query.removeprefix('zip://').removeprefix('zip::').strip('/')
        if query in nodes and nodes[query]['type'] == 'file':
            result = {query: {}}
        else:
            result = {}
            root_parts = query.split('/') if query else []
            for name in sorted(nodes):
                parts = name.split('/')
                if parts[:len(root_parts)] != root_parts:
                    continue
                if not withdirs and nodes[name]['type'] == 'directory':
                    continue
                if depth is not None and len(parts) - len(root_parts) > depth:
                    continue
                result[name] = nodes[name]
        result = {k: result[k] for k in sorted(result)}
        return {'ok': result, 'order': list(result)} if detail else {'ok': list(result)}

    out = {}
    if case == 'bundle':
        files = {}
        for year in range(2023, 2023 + (size + 671) // 672):
            for month in range(1, 13):
                for day in range(1, 29):
                    for part in range(2):
                        if len(files) >= size:
                            break
                        name = f'dataset/year={year}/month={month:02d}/day={day:02d}/part-{part:04d}.parquet'
                        files[name] = (year + month * 3 + day * 5 + part + seed) % 61 + 8
        files.update({'dataset/_SUCCESS': 0, 'dataset/_metadata': 40})
        nodes = tree(files)
        out['find_all'] = find(nodes, '')
        out['find_2024'] = find(nodes, 'dataset/year=2024')
        out['find_dirs'] = find(nodes, 'dataset', withdirs=True)
        out['glob'] = {'ok': sorted(name for name in files if fnmatch.fnmatchcase(name, 'dataset/year=2024/month=0*/day=*/*.parquet'))}
        ordered = sorted(files)
        out['du'] = {'ok': {name: files[name] for name in ordered}, 'order': ordered}
        out['find_d2'] = find(nodes, 'dataset', withdirs=True, depth=2)
        out['n'] = len(files)
        out['archive_unchanged'] = True
    elif case == 'edges':
        archives = {
            'empty': tree({}),
            'plain': tree({'a/b/f1': 1, 'a/bc/f2': 2, 'a/b/c/d/f3': 3, 'top': 1, 'a/b/c/f4': 4}),
            'dirs': tree({'a/b/f1': 1, 'x/y/f2': 2}, ('a/', 'a/b/', 'a/empty/', 'x/', 'x/y/', 'x/y/z/')),
        }
        for name, nodes in archives.items():
            for query in ['', '/', 'a', 'a/', '/a', 'zip://a', 'a/b', 'a/bc', 'a/b/f1', 'top', 'nope', 'a/b/c', 'x', 'x/y', 'x/y/z', 'a/empty']:
                for withdirs in (False, True):
                    for depth in (None, 0, 1, 2, 3):
                        for detail in (False, True):
                            key = f'{name}|{query}|{withdirs}|{depth}|{detail}'
                            out[key] = find(nodes, query, withdirs, depth, detail)
    else:
        raise ValueError(case)
    encoded = json.dumps(out, sort_keys=True, separators=(',', ':')).encode()
    return {'count': len(out), 'sha256': hashlib.sha256(encoded).hexdigest(), 'outputs': out if case == 'bundle' and size <= 2 else None}
