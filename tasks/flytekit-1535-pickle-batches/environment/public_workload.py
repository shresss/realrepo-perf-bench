"""Real local workflow transport with an ordinary importable user fixture module."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile

def canonical(value):
    if isinstance(value, dict):
        return ['dict', [[canonical(k), canonical(v)] for k, v in sorted(value.items())]]
    if isinstance(value, tuple):
        return ['tuple', [canonical(v) for v in value]]
    if isinstance(value, list):
        return ['list', [canonical(v) for v in value]]
    return [type(value).__name__, value]


def content_digest(value):
    return hashlib.sha256(json.dumps(canonical(value), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def make_records(case, size, seed):
    records = []
    for i in range(size):
        v = (i * 101 + seed * 37) % 100003
        if case == 'nested':
            item = [v, {'slot': i % 5, 'values': [i, -v]}, ('tag', i % 7)]
        else:
            label = ('résumé 東京 π ' if case == 'unicode' else 'record ') + str(v)
            item = {'id': i, 'value': v, 'label': label, 'nested': {'enabled': bool(i % 2), 'data': [v, -v, None]}, 'pair': (i % 3, seed % 11)}
        records.append(item)
    return records


# Same user task/workflow bodies as the initial fixture; imported normally.
_TASK_MODULE_SOURCE = "from typing import Any, List\nimport hashlib\nimport json\nfrom flytekit import task, workflow\n\n\ndef canonical(value):\n    if isinstance(value, dict):\n        return ['dict', [[canonical(k), canonical(v)] for k, v in sorted(value.items())]]\n    if isinstance(value, tuple):\n        return ['tuple', [canonical(v) for v in value]]\n    if isinstance(value, list):\n        return ['list', [canonical(v) for v in value]]\n    return [type(value).__name__, value]\n\n\ndef content_digest(value):\n    return hashlib.sha256(json.dumps(canonical(value), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()\n\n\n@task(disable_deck=True)\ndef pass_records(items: List[Any]) -> List[Any]:\n    return items\n\n\n@task(disable_deck=True)\ndef digest_records(items: List[Any]) -> str:\n    return content_digest(items)\n\n\n@workflow\ndef record_workflow(items: List[Any]) -> str:\n    return digest_records(items=pass_records(items=items))\n\n\n@task(disable_deck=True)\ndef copy_numbers(items: List[int]) -> List[int]:\n    return items\n\n\n@workflow\ndef number_workflow(items: List[int]) -> List[int]:\n    return copy_numbers(items=items)\n"


def run(case, size, seed):
    from flytekit.core.context_manager import FlyteContextManager
    from flytekit.core.data_persistence import FileAccessProvider

    if size < 1:
        raise ValueError('nonempty input batches required')
    records = make_records(case, size, seed)
    with tempfile.TemporaryDirectory(prefix='flyte-list-transport-') as root:
        module_name = 'afterquery_record_workflow_fixture'
        module_dir = Path(root) / 'user_module'
        module_dir.mkdir()
        (module_dir / (module_name + '.py')).write_text(_TASK_MODULE_SOURCE)
        sys.path.insert(0, str(module_dir))
        try:
            user_module = importlib.import_module(module_name)
            fa = FileAccessProvider(local_sandbox_dir=root + '/sandbox', raw_output_prefix=root + '/objects')
            builder = FlyteContextManager.current_context().with_file_access(fa)
            with FlyteContextManager.with_context(builder):
                if case == 'floor':
                    return {'floor': True, 'count': len(records)}
                if case == 'typed':
                    values = [x['value'] for x in records]
                    actual = user_module.number_workflow(items=values)
                    return {'count': len(actual), 'digest': content_digest(actual)}
                actual = user_module.record_workflow(items=records)
                return {'count': len(records), 'digest': actual, 'input_unchanged': content_digest(records)}
        finally:
            sys.path.remove(str(module_dir))
            sys.modules.pop(module_name, None)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--size', type=int, required=True)
    parser.add_argument('--seed', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
