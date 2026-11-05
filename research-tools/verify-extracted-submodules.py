"""Re-read extracted submodule files and compare their bytes to pinned Git blobs."""
import hashlib
import json
import os
from pathlib import Path

project = Path(__file__).resolve().parent.parent
source = project / 'ardupilot-source/ardupilot-master'
archive_dir = project / 'research-tools/submodule-archives'
manifest = json.loads((project / 'ardupilot-source/extracted-submodules.json').read_text())
names = {'modules/waf':'waf', 'modules/mavlink':'mavlink', 'modules/mavlink/pymavlink':'pymavlink',
         'modules/DroneCAN/DSDL':'dsdl', 'modules/DroneCAN/dronecan_dsdlc':'dsdlc',
         'modules/DroneCAN/libcanard':'libcanard', 'modules/DroneCAN/pydronecan':'pydronecan',
         'modules/littlefs':'littlefs', 'modules/ChibiOS':'chibios', 'modules/gbenchmark':'gbenchmark',
         'modules/gsoap':'gsoap', 'modules/gtest':'gtest', 'modules/lwip':'lwip',
         'modules/Micro-CDR':'microcdr', 'modules/Micro-XRCE-DDS-Client':'microxrce',
         'modules/DroneCAN/libcanard/drivers/avr/avr-can-lib':'avrcan'}
results = []
for item in manifest:
    name = names[item['path']]
    tree = json.loads((archive_dir / f'{name}-tree.json').read_text(encoding='utf-8'))
    if tree['sha'] != item['sha'] or tree['truncated']:
        raise ValueError(f'tree mismatch {item["path"]}')
    folder = (source / item['path']).resolve()
    io_folder = Path('\\\\?\\' + str(folder)) if os.name == 'nt' else folder
    missing = []
    mismatches = []
    blobs = [x for x in tree['tree'] if x['type'] == 'blob']
    for blob in blobs:
        file = io_folder / blob['path']
        if not file.is_file():
            missing.append(blob['path'])
            continue
        data = file.read_bytes()
        digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        if digest != blob['sha']:
            mismatches.append(blob['path'])
    result = {'path': item['path'], 'commit': item['sha'], 'expected_blobs': len(blobs),
              'missing': missing, 'mismatches': mismatches}
    results.append(result)
    print(f'{item["path"]}: {len(blobs)} checked, missing={len(missing)}, mismatches={len(mismatches)}', flush=True)
    (project / 'ardupilot-source/extracted-submodule-verification.json').write_text(json.dumps(results, indent=2) + '\n')
if any(x['missing'] or x['mismatches'] for x in results):
    raise SystemExit(1)
