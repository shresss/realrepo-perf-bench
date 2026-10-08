"""Independent stdlib oracle for the specified record schema and exact type shape."""
import hashlib
import json


def digest_tree(tree):
    return hashlib.sha256(json.dumps(tree, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def oracle(case, size, seed):
    if case == 'floor':
        return {'floor': True, 'count': size}
    rows = []
    for index in range(size):
        number = (101 * index + 37 * seed) % 100003
        integer = lambda value: ['int', value]
        pair = ['tuple', [integer(index % 3), integer(seed % 11)]]
        if case == 'typed':
            row = integer(number)
        elif case == 'nested':
            row = ['list', [integer(number), ['dict', [[['str', 'slot'], integer(index % 5)], [['str', 'values'], ['list', [integer(index), integer(-number)]]]]], ['tuple', [['str', 'tag'], integer(index % 7)]]]]
        else:
            label = ('résumé 東京 π ' if case == 'unicode' else 'record ') + str(number)
            inner = ['dict', [[['str', 'data'], ['list', [integer(number), integer(-number), ['NoneType', None]]]], [['str', 'enabled'], ['bool', bool(index % 2)]]]]
            row = ['dict', [[['str', 'id'], integer(index)], [['str', 'label'], ['str', label]], [['str', 'nested'], inner], [['str', 'pair'], pair], [['str', 'value'], integer(number)]]]
        rows.append(row)
    digest = digest_tree(['list', rows])
    expected = {'count': size, 'digest': digest}
    if case != 'typed':
        expected['input_unchanged'] = digest
    return expected


# Standard verifier entry point; same independent oracle used in host screens.
expected = oracle
