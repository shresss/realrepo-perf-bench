import hashlib, json

def build_doc(n):
    lines = ['# fleet inventory', 'title = "prod fleet"', '']
    for i in range(n):
        lines += [f'[inventory.hosts.web-{i:04d}]', f'ip = "10.{i // 250}.{i % 250}.{i * 7 % 250}"', f'''role = "{['web', 'db', 'cache', 'queue'][i % 4]}"''', f'zone = "eu-west-{1 + i % 3}"', f'cpus = {2 ** (i % 5)}', f'memory_gb = {4 * (1 + i % 8)}', f'tags = ["tier-{i % 3}", "team-{i % 7}"]', f"enabled = {('true' if i % 5 else 'false')}", f'notes = "host {i} été rack {i % 40}"', '']
    return '\n'.join(lines)
CASES = {'empty': '', 'single_subtable': '[inventory.hosts.a]\nip = "1"\n', 'duplicate_header': '[a.b.c]\nx = 1\n[a.b.c]\ny = 2\n', 'duplicate_key_across_merge': '[a.b.c]\nx = 1\n[a.b]\nc = 2\n', 'unicode': '[inventaire."hôtes"."été"]\nnom = "日本語 😀"\n[inventaire."hôtes".hiver]\nnom = "ß"\n'}

def fixture(case, size, seed):
    if case == 'inventory':
        return build_doc(size).replace('title = "prod fleet"', f'title = "prod fleet {seed}"')
    return CASES[case]

def normal(value):
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))

def run(case, size, seed):
    import tomlkit
    text = fixture(case, size, seed)
    try:
        doc = tomlkit.parse(text)
    except Exception:
        return {'error': True}
    rendered = tomlkit.dumps(doc)
    result = {'error': False, 'data': normal(doc.unwrap()), 'render_sha256': hashlib.sha256(rendered.encode()).hexdigest(), 'roundtrip': rendered == text}
    if case != 'inventory':
        import copy
        copied = copy.deepcopy(doc)
        copied['aq_added'] = {'marker': seed + 11}
        result['copy_independent'] = tomlkit.dumps(doc) == text and 'aq_added' not in doc and (normal(copied.unwrap()).get('aq_added') == {'marker': seed + 11})
    return result
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--case', default='inventory')
    p.add_argument('--size', type=int, default=75)
    p.add_argument('--seed', type=int, default=0)
    a = p.parse_args()
    print(json.dumps(run(a.case, a.size, a.seed), ensure_ascii=False))
