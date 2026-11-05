"""Independently decode failed and successful copied-storage reboot attempts."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
fields = ('seq', 'command', 'param1', 'param2', 'param3', 'param4', 'x', 'y', 'z', 'mission_type')
def decode(path):
    p = ardupilotmega.MAVLink(None); p.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = p.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1
        elif msg.get_type() in ('HEARTBEAT', 'MISSION_COUNT', 'MISSION_ITEM_INT', 'MISSION_ACK'):
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]; found.append(item)
    return found, bad
for case, baseline in (('fence-mission-reboot', 'command-ack-fence_roundtrip_retry'),
                       ('fence-mission-reboot-stable', 'command-ack-fence_roundtrip_stable')):
    out = root / 'sitl-evidence' / case
    source = root / 'sitl-evidence' / baseline
    result = json.loads((out / 'result.json').read_text())
    assert result['binary_sha256'] == sha(root / 'sitl-evidence/archive-built/arducopter')
    assert result['source_summary_sha256'] == sha(source / 'summary.json')
    assert result['source_storage_sha256'] == result['copied_storage_sha256'] == sha(out / 'eeprom-before.bin') == sha(source / 'eeprom.bin')
    assert result['post_shutdown_storage_sha256'] == sha(out / 'eeprom.bin')
    assert result['downlink_sha256'] == sha(out / 'downlink.bin')
    records, bad = decode(out / 'downlink.bin')
    counts = [m for m in records if m['mavpackettype'] == 'MISSION_COUNT' and m['source'] == [1, 1]]
    items = [m for m in records if m['mavpackettype'] == 'MISSION_ITEM_INT' and m['source'] == [1, 1]]
    acks = [m for m in records if m['mavpackettype'] == 'MISSION_ACK' and m['source'] == [1, 1]]
    assert counts and (counts[0]['mission_type'], counts[0]['count']) == (0, 2)
    if case == 'fence-mission-reboot':
        assert result['errors'] == ["RuntimeError('missing item (0, 1)')"] and result['observed'] == {}
        assert [(m['mission_type'], m['seq']) for m in items] == [(0, 0)]
        assert any(m['mission_type'] == 0 and m['type'] == 1 for m in acks)
        outcome = 'incomplete; received mission error after first item'
    else:
        assert result['errors'] == [] and result['startup_wait_seconds'] == 12
        assert [(m['mission_type'], m['count']) for m in counts] == [(0, 2), (1, 4)]
        assert [(m['mission_type'], m['seq']) for m in items] == [(0, 0), (0, 1), (1, 0), (1, 1), (1, 2), (1, 3)]
        actual = {str(typ): [{k: m[k] for k in fields} for m in items if m['mission_type'] == typ] for typ in (0, 1)}
        original = json.loads((source / 'summary.json').read_text())
        expected = {str(typ): [{k: m[k] for k in fields} for m in [v for v in original['received'] if v['mission_type'] == typ][:count]] for typ, count in ((0, 2), (1, 4))}
        assert actual == expected == result['expected'] == result['observed']
        outcome = 'six selected mission and fence fields matched after reboot'
    summary = {'scope': 'Standalone MAVLink client, copied simulator storage; not a physical controller', 'outcome': outcome,
               'result': result, 'source_summary_sha256': sha(source / 'summary.json'), 'readback_source_sha256': sha(out / 'readback-source.py'),
               'counts': counts, 'items': items, 'acks': acks, 'bad_data_fragments': bad}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(case, outcome)
