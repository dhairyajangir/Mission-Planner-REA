"""Check selected-type evidence coverage against the main PE TypeDef inventory."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent / 'mission-planner-binary-evidence'
inventory = json.loads((root / 'rea-main-all-members.json').read_text(encoding='utf-8'))
expected = {x['token']: x for x in inventory['normalized_result']['types'] if x['name'] != '<Module>'}
observed = set()
methods = set()
issues = []
for dirname in ('type-batches', 'nested-type-batches'):
    folder = root / dirname
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['assembly_sha256'] != inventory['subject']['digest']['sha256']:
        raise ValueError('manifest refers to another executable')
    for batch in manifest['batches']:
        if batch['status'] != 'complete':
            issues.append({'path': batch['path'], 'reason': batch['status']})
            continue
        data = json.loads((folder / batch['path']).read_text(encoding='utf-8'))
        n = data['normalized_result']
        if data['subject']['digest']['sha256'] != manifest['assembly_sha256']:
            raise ValueError(f'wrong executable in {batch["path"]}')
        if n['coverage']['state'] != 'complete' or n['selection']['unmatched_type_names']:
            issues.append({'path': batch['path'], 'reason': 'coverage or selection'})
        observed.update(x['token'] for x in n['types'])
        methods.update(x['token'] for x in n['methods'])
missing = [{'token': token, 'name': entry['full_name']} for token, entry in expected.items() if token not in observed]
result = {'assembly_sha256': inventory['subject']['digest']['sha256'],
          'inventory_typedefs_excluding_module': len(expected), 'observed_inventory_typedefs': len(set(expected) & observed),
          'unique_method_tokens': len(methods), 'missing_types': missing, 'issues': issues,
          'limitations': ['Type and method metadata coverage does not establish runtime behavior, full source recovery, dependency coverage, or workflow coverage.',
                          'All metadata tokens are meaningful only for this exact assembly hash.']}
(root / 'rea-main-coverage.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k not in ('missing_types', 'issues', 'limitations')}, indent=2))
print('missing', len(missing), 'issues', len(issues))
