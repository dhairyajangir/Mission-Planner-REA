"""Build small synthetic plan files for the distributed Mission Planner library."""
import copy
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
folder = root / 'sitl-evidence/mission-plan-probe'
folder.mkdir(exist_ok=True)

def item(command, lat, lng, altitude):
    return {'type': 'SimpleItem', 'command': command, 'frame': 3, 'doJumpId': 1,
            'autoContinue': True, 'params': [2, None, 0, 0, lat, lng, altitude]}

simple = item(16, -35.3625, 149.166, 25)
complex_item = {'type': 'ComplexItem', 'complexItemType': 'survey',
                'TransectStyleComplexItem': {'Items': [item(16, -35.362, 149.167, 30),
                                                       item(16, -35.361, 149.168, 35)]}}
plan = {'fileType': 'Plan', 'version': 1, 'mission': {'plannedHomePosition': [-35.363261, 149.16523, 584],
         'items': [simple, complex_item, {'type': 'UnrecognizedItem'}]}}
missing_complex = copy.deepcopy(plan)
del missing_complex['mission']['items'][1]['TransectStyleComplexItem']
short_params = copy.deepcopy(plan)
short_params['mission']['items'][0]['params'] = [2, 0, 0, 0, -35.3625, 149.166]
fixtures = {'valid.plan': plan, 'complex-missing.plan': missing_complex, 'short-params.plan': short_params}
manifest = {}
for name, value in fixtures.items():
    contents = (json.dumps(value, indent=2) + '\n').encode('utf-8')
    path = folder / name
    if path.exists() and path.read_bytes() != contents:
        raise ValueError('existing fixture differs: ' + name)
    path.write_bytes(contents)
    manifest[name] = {'sha256': hashlib.sha256(contents).hexdigest(), 'size': len(contents)}
(folder / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
