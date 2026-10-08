"""BI query-log parsing and column-lineage extraction through sqlparse.parse."""
import hashlib
import json
import random


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _queries(size, seed):
    rng = random.Random(42 + seed)
    result = []
    for statement in range(12):
        columns = []
        for index in range(size):
            r = rng.random()
            name = f'col_{index:04d}'
            columns.append(name if r < .7 else f'f.{name}' if r < .85 else f'{name} metric_{index}')
        result.append(f"SELECT {', '.join(columns)}\nFROM warehouse.fact_events_{statement} f\n"
                      f"WHERE f.event_date >= '2026-01-01' AND f.tenant_id = {statement};")
    return '\n'.join(result)


def run(case, size, seed):
    import sqlparse
    from sqlparse import sql
    if case != 'wide' or size < 2:
        raise ValueError((case, size))
    text = _queries(size, seed)
    statements = sqlparse.parse(text)
    groups, lineage, types = [], [], []
    coherent, parents = True, True

    def visit(token):
        nonlocal coherent, parents
        if token.is_group:
            groups.append([type(token).__name__, len(token.tokens), token.value])
            coherent = coherent and token.value == ''.join(leaf.value for leaf in token.flatten())
            for child in token.tokens:
                parents = parents and child.parent is token
                visit(child)

    for statement in statements:
        visit(statement)
        types.append(statement.get_type())
        projected = [token for token in statement.tokens if isinstance(token, sql.IdentifierList)]
        if len(projected) != 1:
            raise AssertionError('one projection list required')
        lineage.append([[token.get_parent_name(), token.get_real_name(), token.get_alias(), token.value]
                        for token in projected[0].get_identifiers()])
    roundtrip = ''.join(str(statement) for statement in statements)
    return {'statements': len(statements), 'columns': sum(map(len, lineage)),
            'types': types, 'lineage': _digest(lineage), 'group_tree': _digest(groups),
            'group_count': len(groups), 'values_coherent': coherent, 'parents_coherent': parents,
            'roundtrip': hashlib.sha256(roundtrip.encode()).hexdigest(), 'source_unchanged': roundtrip == text}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', default='wide')
    parser.add_argument('--size', type=int, default=2400)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
