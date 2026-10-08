"""Stable reconciliation of typed imported snapshots and public equality semantics."""
import hashlib
import json
import sys
from pathlib import Path


def _attrs():
    # The driver may precede the role snapshot on sys.path; the public aid runs in /app.
    selected = None
    for entry in [*sys.path, str(Path.cwd())]:
        root = Path(entry)
        if (root / 'src/attr').is_dir():
            selected = (root / 'src').resolve()
            sys.path.insert(0, str(selected))
            break
    if selected is None:
        raise RuntimeError('attrs source snapshot not found')
    import attr
    if not Path(attr.__file__).resolve().is_relative_to(selected):
        raise RuntimeError('attrs did not import from the role source snapshot')
    return attr


def run(case, size, seed):
    attr = _attrs()
    if case == 'reconcile':
        names = ['account_id'] + [f'field_{j:02d}' for j in range(1, 64)]
        Record = attr.make_class('ImportedSnapshot', {name: attr.ib() for name in names}, slots=True)
        values = []
        for i in range(size):
            if i > 0 and i % 10 == 0:
                row = list(values[i - 1])
            elif i > 1 and i % 10 == 1:
                row = list(values[i - 2]); row[-1] = str(row[-1]) + '-revision'
            else:
                row = [f'account-{i + seed}'] + [(i * 37 + j + seed) % 997 if j % 3 else f'category-{(i + j + seed) % 113}' for j in range(1, 64)]
            values.append(row)
        records = [Record(*row) for row in values]
        seen, positions = [], []
        for i, row in enumerate(records):
            if row not in seen:
                seen.append(row); positions.append(i)
        payload = {'positions': positions, 'rows': [[getattr(row, name) for name in names] for row in seen]}
        unchanged = [[getattr(row, name) for name in names] for row in records] == values
        return {'count': len(seen), 'sha256': hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), 'input_unchanged': unchanged}
    if case == 'semantics':
        out = []
        for slots in (False, True):
            for eq_key in (None, abs):
                C = attr.make_class('Record', {'a': attr.ib(eq=eq_key or True), 'b': attr.ib(), 'ignore': attr.ib(eq=False)}, slots=slots)
                x = C(-4, 2, 'x'); same = C(4 if eq_key else -4, 2, 'y'); last = C(-4, 3, 'x')
                out.extend([x == same, x != same, x == last, x != last, x.__eq__(object()) is NotImplemented])
                x.b = 3; out.extend([x == last, x != last])
                Empty = attr.make_class('Empty', {}, slots=slots)
                out.extend([Empty() == Empty(), Empty() != Empty()])
            C = attr.make_class('Wide', {f'f{i}': attr.ib() for i in range(64)}, slots=slots)
            same = list(range(64)); a = C(*same)
            for pos in range(64):
                changed = list(same); changed[pos] += 1
                out.extend([a == C(*changed), a != C(*changed)])
            out.extend([a == C(*same), a != C(*same)])
        return {'observations': out}
    raise ValueError(case)

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',default='reconcile')
    parser.add_argument('--size',type=int,default=2000)
    parser.add_argument('--seed',type=int,default=0)
    args=parser.parse_args()
    print(json.dumps(run(args.case,args.size,args.seed),sort_keys=True))
