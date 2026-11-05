"""Summarize two saved SITL runs without inferring the cause of termination."""
from pathlib import Path
import hashlib, json, math, os, sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root/'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega as mav
for form in ('int','float'):
    run = root/('sitl-evidence/command-ack-wpl_nan_'+form)
    relay = json.loads((run/'relay-result.json').read_text())
    def read(name):
        raw = (run/name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == relay['capture_sha256'][name]
        parser = mav.MAVLink(None); parser.robust_parsing = True
        result = []
        for b in raw:
            m = parser.parse_char(bytes([b]))
            if m and m.get_type() != 'BAD_DATA': result.append(m)
        return result
    sent, received = read('to_sitl_output.bin'), read('to_client_output.bin')
    log = (run/'probe.log').read_text(errors='replace')
    assert 'FIXTURE_COUNT=2 LAT_IS_NAN=True' in log and 'BASELINE_RESULTS=MAV_MISSION_ACCEPTED,MAV_MISSION_ACCEPTED' in log
    assert 'BASELINE_ITEM1=-35.363,149.1655,20' in log and 'REPLACE_FIRST=MAV_MISSION_ACCEPTED' in log
    acks = [m.to_dict() for m in received if m.get_type() == 'MISSION_ACK' and m.get_srcSystem() == 1 and m.get_srcComponent() == 1]
    if form == 'int':
        items = [m.to_dict() for m in sent if m.get_type() == 'MISSION_ITEM_INT' and m.seq == 1 and m.x == -2147483648]
        assert len(items) == 1 and any(m['type'] == 10 for m in acks)
        assert 'NAN_RESULT=MAV_MISSION_INVALID_PARAM5_X' in log and 'AFTER_ITEM1=-35.363,149.1655,20' in log
        assert (run/'probe-exit.txt').read_text().strip() == '0' and relay['closed_by'] == 'client'
    else:
        items = [m.to_dict() for m in sent if m.get_type() == 'MISSION_ITEM' and m.seq == 1 and math.isnan(m.x)]
        assert items and 'NAN_EXCEPTION=System.TimeoutException' in log and 'UNHANDLED=System.TimeoutException: Timeout on read - getWPCount' in log
        assert (run/'probe-exit.txt').read_text().strip() == '1' and relay['closed_by'] == 'sitl'
        assert 'ERROR: Floating point exception - aborting' in (run/'sitl.log').read_text(errors='replace')
    summary = {'form':form, 'item_count':len(items), 'sent_item':items[0], 'ack_types':[m['type'] for m in acks],
               'relay_closed_by':relay['closed_by'],'probe_exit':int((run/'probe-exit.txt').read_text()),
               'post_upload_readback_completed':form == 'int',
               'files':{n:hashlib.sha256((run/n).read_bytes()).hexdigest() for n in ('probe.log','probe-source.cs','input.waypoints','sitl.log','to_sitl_output.bin','to_client_output.bin')}}
    if form == 'float': summary['sent_item']['x'] = 'NaN'
    (run/'nan-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))
