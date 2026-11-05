"""Validate captured signed heartbeat, replay, and corrupted signature injection."""
import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;out=root/'sitl-evidence/signing-serial1-replay-match'
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
relay=json.loads((out/'relay-result.json').read_text());key=hashlib.sha256(b'synthetic-signing-seed').digest()
assert relay['case']=='match' and not relay['errors'] and relay['closed_by']=='client' and relay['test_key_hex']==key.hex()
assert relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
assert all(sha(out/n)==h for n,h in relay['capture_sha256'].items())
sample=bytes.fromhex(relay['configured_secondary']['raw_hex']);bad=sample[:-1]+bytes([sample[-1]^1])
assert len(sample)==34 and sample[0]==253 and sample[2]&1
assert hashlib.sha256(key+sample[:-6]).digest()[:6]==sample[-6:]
assert hashlib.sha256(key+bad[:-6]).digest()[:6]!=bad[-6:]
assert hashlib.sha256(sample).hexdigest()==relay['injected_sample_sha256']
assert hashlib.sha256(bad).hexdigest()==relay['injected_bad_sha256']
assert (out/'injected.bin').read_bytes()==sample+sample+bad
assert (out/'downlink.bin').read_bytes().startswith(sample+sample+bad)
assert sample in (out/'bootstrap-secondary-down.bin').read_bytes()
parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;frames=[]
for byte in (out/'injected.bin').read_bytes():
    m=parser.parse_char(bytes([byte]))
    if m is not None and m.get_type()!='BAD_DATA':frames.append(m)
assert len(frames)==3 and all(m.get_type()=='HEARTBEAT' and m.get_srcSystem()==1 and not(m.base_mode&128) for m in frames)
assert [bytes(m.get_msgbuf()) for m in frames]==[sample,sample,bad]
log=(out/'probe.log').read_text(encoding='utf8',errors='replace')
assert (out/'probe-exit.txt').read_text().strip()=='0'
assert all(s in log for s in ['OPEN_RETURNED=True ISOPEN=True SELECTED=1:1','ADOPTED=True KEY_NULL=False','PARAM=0','SERIAL1_PROBE_COMPLETE=True'])
assert log.count('HB_SHA='+relay['injected_sample_sha256'])==2
assert log.count('HB_SHA='+relay['injected_bad_sha256'])==0
assert log.count('Packet failed signature but passed crc')>=1
summary={'scope':'One disarmed Copter SITL session; same authentic signed heartbeat injected twice, then signature-corrupted copy',
         'relay':relay,'sample_sha256':hashlib.sha256(sample).hexdigest(),'bad_sha256':hashlib.sha256(bad).hexdigest(),
         'sample_event_count':2,'bad_event_count':0,'signature_failure_log_count':log.count('Packet failed signature but passed crc'),
         'hashes':{n:sha(out/n) for n in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt','relay-source.py']},
         'library_hashes':{n:sha(root/'mission-planner-portable'/n) for n in ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','SigningSerial1ReplayProbe.exe.config']}}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('Accepted identical heartbeat twice; altered signature logged and absent from event')
