"""Compare synthetic MAVLink signing on two local disposable SITL serial channels."""
import hashlib,json,os,select,socket,subprocess,sys,time,traceback
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega as mav
out=root/'sitl-evidence/signing-channel-sitl-2';out.mkdir(exist_ok=False)
binary=root/'sitl-evidence/archive-built/arducopter'
key=hashlib.sha256(b'synthetic-channel-signing-key').digest();wrong=hashlib.sha256(b'synthetic-channel-wrong-key').digest()
epoch=int((time.time()-1420070400)*100000)
result={'scope':'Standalone synthetic MAVLink client, disposable disarmed Copter SITL, two local serial endpoints',
        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'test_key_hex':key.hex(),'wrong_key_hex':wrong.hex(),
        'events':[],'errors':[]}
proc=None;log=(out/'sitl.log').open('wb');sockets={};files={};parsers={}
def record(name,data):
    files[name].write(data);files[name].flush()
def connect(port):
    deadline=time.monotonic()+30
    while True:
        if proc.poll() is not None: raise RuntimeError('SITL exited during startup')
        try:
            s=socket.create_connection(('127.0.0.1',port),timeout=1);s.setblocking(False);return s
        except OSError:
            if time.monotonic()>deadline:raise
            time.sleep(.25)
def drain(channel,seconds):
    parser=parsers[channel];end=time.monotonic()+seconds;messages=[]
    while time.monotonic()<end:
        if not select.select([sockets[channel]],[],[],min(.2,max(0,end-time.monotonic())))[0]:continue
        chunk=sockets[channel].recv(65536)
        if not chunk:raise RuntimeError('connection closed '+channel)
        record(channel+'-downlink',chunk)
        for byte in chunk:
            msg=parser.parse_char(bytes([byte]))
            if msg is None or msg.get_type()=='BAD_DATA':continue
            if msg.get_type() in ('HEARTBEAT','PARAM_VALUE','STATUSTEXT'):
                raw=bytes(msg.get_msgbuf());signed=raw[0]==253 and bool(raw[2]&1)
                d=msg.to_dict();d['source']=[msg.get_srcSystem(),msg.get_srcComponent()];d['signed']=signed;d['raw_hex']=raw.hex()
                if signed:d['valid_test_key']=hashlib.sha256(key+raw[:-6]).digest()[:6]==raw[-6:]
                messages.append(d)
    return messages
def send(channel,data):
    sockets[channel].sendall(data);record(channel+'-uplink',data)
def encoder(secret=None,timestamp=epoch+12000000):
    e=mav.MAVLink(None,srcSystem=255,srcComponent=190)
    if secret is not None:
        e.signing.secret_key=secret;e.signing.sign_outgoing=True;e.signing.link_id=19;e.signing.timestamp=timestamp
    return e
def frame(secret=None,timestamp=epoch+12000000):
    e=encoder(secret,timestamp)
    return e.param_request_read_encode(1,1,b'LOG_DISARMED',-1).pack(e)
try:
    proc=subprocess.Popen([str(binary),'-I','180','--model','quad','--home=-35.363261,149.165230,584,0'],cwd=out,stdout=log,stderr=subprocess.STDOUT)
    for name,port in [('channel0',7560),('channel1',7562)]:
        sockets[name]=connect(port);parsers[name]=mav.MAVLink(None);parsers[name].robust_parsing=True
        for suffix in ('uplink','downlink'):files[name+'-'+suffix]=(out/(name+'-'+suffix+'.bin')).open('wb')
    for name in sockets:
        initial=drain(name,5)
        hb=[m for m in initial if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
        if not hb or any(m['base_mode']&128 for m in hb):raise RuntimeError('no disarmed heartbeat '+name)
        result['events'].append({'channel':name,'case':'initial','heartbeats':hb})
    e=encoder();setup=e.setup_signing_encode(1,1,key,epoch).pack(e)
    send('channel0',setup);result['setup_hex']=setup.hex()
    for name in sockets:drain(name,2)
    for channel in sockets:
        valid=frame(key,epoch+12000000+(0 if channel=='channel0' else 200000))
        tests=[('unsigned',frame()),('bad_signature',frame(wrong,epoch+11000000)),('valid',valid),('replay',valid)]
        for label,packet in tests:
            drain(channel,.2);down_start=files[channel+'-downlink'].tell();up_start=files[channel+'-uplink'].tell()
            send(channel,packet);messages=drain(channel,1.5)
            replies=[m for m in messages if m['mavpackettype']=='PARAM_VALUE' and m['param_id']=='LOG_DISARMED' and m['source']==[1,1]]
            result['events'].append({'channel':channel,'case':label,'packet_hex':packet.hex(),'responses':replies,
                                     'uplink_start':up_start,'uplink_end':files[channel+'-uplink'].tell(),
                                     'downlink_start':down_start,'downlink_end':files[channel+'-downlink'].tell()})
            print(channel,label,'responses',len(replies),flush=True)
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    for s in sockets.values():s.close()
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
    log.close()
    for f in files.values():f.close()
    result['capture_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.bin') if p.name!='eeprom.bin'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if result['errors']:raise SystemExit(1)
