"""Compare completed REA batches with independent Cecil type/method counts."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
base = root / 'mission-planner-binary-evidence'
relative = sys.argv[1] if len(sys.argv) > 1 else 'Accord.Statistics.dll'
if Path(relative).name != relative or relative in ('.', '..'):
    raise ValueError('expected a root-level assembly filename')
slug = Path(relative).stem.lower().replace('.', '-')
source = base / (slug + ('-mixed-batches' if '--mixed' in sys.argv[2:] else '-batches'))
manifest = json.loads((source / 'manifest.json').read_text())
binary = root / 'mission-planner-portable' / relative
if hashlib.sha256(binary.read_bytes()).hexdigest() != manifest['assembly_sha256']:
    raise ValueError('assembly hash changed')
rows = [line.split('\t') for line in (base / 'remaining-managed-members' / (slug + '-cecil-types.tsv')).read_text(encoding='utf-8').splitlines()]
expected = {int(x[0], 16): {'name': x[1], 'method_count': int(x[4])} for x in rows if x[2] != '<Module>'}
types, methods, errors = set(), {}, []
for batch in manifest['batches']:
    if batch['status'] != 'complete':
        continue
    with gzip.open(source / batch['evidence'], 'rt', encoding='utf-8') as f:
        data = json.load(f)
    if data['subject']['digest']['sha256'] != manifest['assembly_sha256'] or data['normalized_result']['coverage']['state'] != 'complete':
        errors.append(batch['evidence'])
        continue
    n = data['normalized_result']
    types.update(int(t['token'], 16) for t in n['types'])
    for method in n['methods']:
        token = int(method['token'], 16)
        declaring = int(method['declaring_type_token'], 16)
        if token in methods and methods[token] != declaring:
            errors.append('conflicting method ' + method['token'])
        methods[token] = declaring
counts = {token: 0 for token in expected}
for declaring in methods.values():
    if declaring in counts:
        counts[declaring] += 1
under = [{'token': f'0x{token:08x}', 'name': row['name'], 'expected': row['method_count'],
          'observed': counts[token]} for token, row in expected.items() if counts[token] != row['method_count']]
missing = [{'token': f'0x{token:08x}', 'name': expected[token]['name']} for token in sorted(set(expected) - types)]
summary = {'assembly_sha256': manifest['assembly_sha256'], 'expected_types': len(expected),
           'expected_methods': sum(x['method_count'] for x in expected.values()),
           'observed_types': len(types & set(expected)), 'observed_methods': len(methods),
           'unexpected_types': [f'0x{x:08x}' for x in sorted(types - set(expected))],
           'missing_types': missing, 'method_count_mismatches': under, 'errors': errors,
           'complete_batches': sum(x['status'] == 'complete' for x in manifest['batches']),
           'partial_batches': sum(x['status'] != 'complete' for x in manifest['batches'])}
summary['complete'] = not (summary['unexpected_types'] or missing or under or errors or summary['partial_batches'])
(source / 'coverage-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({key: value for key, value in summary.items() if key not in ('missing_types', 'method_count_mismatches')}, indent=2))
