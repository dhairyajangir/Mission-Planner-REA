"""Independently decode command and ACK captures from local SITL loss tests."""
import hashlib
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

def decode(path):
    parser = ardupilotmega.MAVLink(None)
    parser.robust_parsing = True
    messages, bad = [], 0
    for b in path.read_bytes():
        msg = parser.parse_char(bytes([b]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        if msg.get_type() in ('COMMAND_LONG', 'COMMAND_ACK') and msg.command == 510:
            item = msg.to_dict()
            item['source_system'] = msg.get_srcSystem()
            item['source_component'] = msg.get_srcComponent()
            messages.append(item)
    return messages, bad

expected = {'normal': ([0], 0, 1), 'drop_one': ([0, 1], 1, 1), 'drop_all': ([0, 1, 2, 3], 4, 0)}
for case, (confirmations, drops, delivered) in expected.items():
    run = root / 'sitl-evidence' / ('command-ack-' + case)
    relay = json.loads((run / 'relay-result.json').read_text())
    assert relay['case'] == case and relay['errors'] == [] and relay['closed_by'] == 'client'
    assert relay['buffered_bytes_at_close'] == 0 and relay['dropped_acks'] == drops
    for name, digest in relay['capture_sha256'].items():
        assert hashlib.sha256((run / name).read_bytes()).hexdigest() == digest
    requests, up_bad = decode(run / 'to_sitl_output.bin')
    received, in_bad = decode(run / 'to_client_input.bin')
    forwarded, out_bad = decode(run / 'to_client_output.bin')
    dropped, drop_bad = decode(run / 'dropped.bin')
    assert [m['confirmation'] for m in requests] == confirmations
    assert all(m['target_system'] == 1 and m['target_component'] == 1 and m['param1'] == 30 for m in requests)
    assert len(received) == len(confirmations) and len(dropped) == drops and len(forwarded) == delivered
    assert all(m['source_system'] == 1 and m['source_component'] == 1 and m['result'] == 0 for m in received)
    log = (run / 'probe.log').read_text(encoding='utf-16', errors='replace')
    outcome = 'COMMAND_TIMEOUT=Timeout on read - doCommand' if case == 'drop_all' else 'COMMAND_RESULT=True'
    assert 'OPEN=True SELECTED=1:1' in log and outcome in log
    summary = {'scope': 'Original Mission Planner MAVLink library and disposable Copter SITL; frame-aware ACK-loss relay',
               'case': case, 'relay': relay, 'requests': requests, 'received_acks': received,
               'forwarded_acks': forwarded, 'dropped_acks': dropped,
               'bad_data_fragments': {'to_sitl': up_bad, 'to_client_input': in_bad,
                                      'to_client_output': out_bad, 'dropped': drop_bad},
               'verified_probe_lines': ['OPEN=True SELECTED=1:1', outcome]}
    (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(case, 'requests', confirmations, 'dropped', drops, 'forwarded', delivered, 'bad', in_bad)
