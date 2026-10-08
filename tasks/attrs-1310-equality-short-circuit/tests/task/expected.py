"""Independent stdlib set model of stable complete-row deduplication."""
import hashlib
import json


def expected(case, size, seed):
    if case == 'reconcile':
        incoming = []
        for index in range(size):
            position = index % 10
            if index and position == 0:
                item = incoming[-1]
            elif index > 1 and position == 1:
                item = incoming[index - 2][:-1] + (str(incoming[index - 2][-1]) + '-revision',)
            else:
                cells = [f'account-{index + seed}']
                for field in range(1, 64):
                    if field % 3 == 0:
                        cells.append(f'category-{(index + field + seed) % 113}')
                    else:
                        cells.append((index * 37 + field + seed) % 997)
                item = tuple(cells)
            incoming.append(item)
        encountered, positions, rows = set(), [], []
        for index, row in enumerate(incoming):
            if row in encountered:
                continue
            encountered.add(row); positions.append(index); rows.append(list(row))
        payload = {'positions': positions, 'rows': rows}
        return {'count': len(rows), 'sha256': hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), 'input_unchanged': True}
    if case == 'semantics':
        per_key = [True, False, False, True, True, True, False, True, False]
        per_storage = per_key * 2 + [False, True] * 64 + [True, False]
        return {'observations': per_storage * 2}
    raise ValueError(case)
