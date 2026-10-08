"""Independent stdlib grammar model; never imports sqlparse or reads golden outputs."""
import hashlib
import json
import random


def expected(case, size, seed):
    if case != 'wide' or size < 2:
        raise ValueError((case, size))
    rng = random.Random(42 + seed)
    groups, lineage, texts = [], [], []
    for statement in range(12):
        columns, identifiers, column_groups = [], [], []
        for index in range(size):
            r = rng.random()
            name = f'col_{index:04d}'
            parent, alias = None, None
            if r < .7:
                column, children = name, 1
            elif r < .85:
                parent, column, children = 'f', f'f.{name}', 3
            else:
                alias = f'metric_{index}'
                column, children = f'{name} {alias}', 3
            columns.append(column)
            identifiers.append([parent, name, alias, column])
            column_groups.append(['Identifier', children, column])
            if alias is not None:
                column_groups.append(['Identifier', 1, alias])
        projection = ', '.join(columns)
        table = f'warehouse.fact_events_{statement} f'
        first = "f.event_date >= '2026-01-01'"
        second = f'f.tenant_id = {statement}'
        where = f'WHERE {first} AND {second};'
        text = f'SELECT {projection}\nFROM {table}\n{where}'
        # Statement splitting preserves the inter-statement newline as a token.
        groups.append(['Statement', 9 if statement == 0 else 10, text if statement == 0 else '\n' + text])
        groups.append(['IdentifierList', 3 * size - 2, projection])
        groups.extend(column_groups)
        groups.extend([['Identifier', 5, table], ['Identifier', 1, 'f'], ['Where', 8, where],
                       ['Comparison', 5, first], ['Identifier', 3, 'f.event_date'],
                       ['Comparison', 5, second], ['Identifier', 3, 'f.tenant_id']])
        texts.append(text)
        lineage.append(identifiers)
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'statements': 12, 'columns': 12 * size, 'types': ['SELECT'] * 12,
            'lineage': digest(lineage), 'group_tree': digest(groups), 'group_count': len(groups),
            'values_coherent': True, 'parents_coherent': True,
            'roundtrip': hashlib.sha256('\n'.join(texts).encode()).hexdigest(), 'source_unchanged': True}
