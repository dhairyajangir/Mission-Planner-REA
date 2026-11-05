"""Independently decode mode-setting frames and disarmed SITL heartbeats."""
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
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for value in path.read_bytes():
        msg = parser.parse_char(bytes([value]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        if msg.get_type() in ('HEARTBEAT', 'SET_MODE', 'COMMAND_LONG', 'COMMAND_ACK'):
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
            found.append(item)
    return found, bad

cases = {'normal': (0, 0, 4), 'drop_cmd': (1, 0, 4), 'drop_legacy': (0, 2, 4), 'drop_all': (1, 2, 0)}
for case, (cmd_drop, legacy_drop, final) in cases.items():
    out = root / 'sitl-evidence' / ('flight-mode-' + case)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == 'mode_' + case and relay['errors'] == [] and relay['closed_by'] == 'client'
    assert relay['buffered_bytes_at_close'] == 0
    assert relay['mode_packets'] == {'command_seen': 1, 'command_dropped': cmd_drop,
                                     'legacy_seen': 2, 'legacy_dropped': legacy_drop}
    for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    incoming, input_bad = decode(out / 'to_sitl_input.bin')
    forwarded, output_bad = decode(out / 'to_sitl_output.bin')
    dropped, dropped_bad = decode(out / 'dropped.bin')
    downlink, down_bad = decode(out / 'to_client_output.bin')
    def selected(items):
        return [m for m in items if m['mavpackettype'] == 'SET_MODE' or
                (m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 176)]
    sent, delivered, lost = map(selected, (incoming, forwarded, dropped))
    assert [m['mavpackettype'] for m in sent] == ['COMMAND_LONG', 'SET_MODE', 'SET_MODE']
    assert sent[0]['source'] == [255, 190] and sent[0]['target_system'] == 1 and sent[0]['target_component'] == 1
    assert sent[0]['param1'] == 1 and sent[0]['param2'] == 4
    assert all(m['source'] == [255, 190] and m['target_system'] == 1 and m['base_mode'] == 1 and m['custom_mode'] == 4 for m in sent[1:])
    assert len(delivered) == 3 - cmd_drop - legacy_drop and len(lost) == cmd_drop + legacy_drop
    heartbeats = [m for m in downlink if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
    assert heartbeats and all((m['base_mode'] & 128) == 0 for m in heartbeats)
    assert any(m['custom_mode'] == 0 for m in heartbeats)
    assert (any(m['custom_mode'] == 4 for m in heartbeats) if final == 4 else all(m['custom_mode'] == 0 for m in heartbeats))
    log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
    lines = ['OPEN=True SELECTED=1:1', 'INITIAL_MODE=0 ARMED=False', 'SET_MODE_RETURNED', 'FINAL_MODE=%d ARMED=False' % final]
    assert all(line in log for line in lines)
    summary = {'scope': 'Original library, disarmed disposable Copter SITL, controlled mode-packet loss',
               'case': case, 'relay': relay, 'sent': sent, 'delivered': delivered, 'dropped': lost,
               'heartbeats': heartbeats, 'final_observed_mode': final,
               'bad_data_fragments': {'uplink_input': input_bad, 'uplink_output': output_bad, 'dropped': dropped_bad, 'downlink': down_bad},
               'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(case, 'sent', len(sent), 'delivered', len(delivered), 'final heartbeat mode', final)
