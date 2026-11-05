"""Provision synthetic signing on disposable SITL SERIAL0, relay SERIAL1 to local client."""
import hashlib,json,os,select,socket,subprocess,sys,time,traceback
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega as mav
mode=os.environ['SIGNING_CASE'];instance=int(os.environ['SIGNING_INSTANCE'])
if mode not in ('match','missing') or instance not in (179,180):raise ValueError('case/instance')
out=root/'sitl-evidence'/('signing-serial1-replay-'+mode);out.mkdir(exist_ok=False)
binary=root/'sitl-evidence/archive-built/arducopter';key=hashlib.sha256(b'synthetic-signing-seed').digest()
result={'scope':'Disposable Copter SITL; synthetic key provisioned on SERIAL0; local relay to SERIAL1',
        'case':mode,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'test_key_hex':key.hex(),'errors':[]}
base=5760+10*instance;proc=listener=client=primary=secondary=log=None;files={}
def connect(port):
    deadline=time.monotonic()+30
    while True:
        if proc.poll() is not None:raise RuntimeError('SITL exited')
        try:return socket.create_connection(('127.0.0.1',port),timeout=1)
        except OSError:
            if time.monotonic()>deadline:raise
            time.sleep(.25)
def wait_heartbeat(sock,path,require_signed=False):
    parser=mav.MAVLink(None);parser.robust_parsing=True;deadline=time.monotonic()+12
    with path.open('ab') as f:
        while time.monotonic()<deadline:
            if not select.select([sock],[],[],.25)[0]:continue
            chunk=sock.recv(65536)
            if not chunk:raise RuntimeError('bootstrap connection closed')
            f.write(chunk);f.flush()
            for b in chunk:
                m=parser.parse_char(bytes([b]))
                if m is None or m.get_type()!='HEARTBEAT' or m.get_srcSystem()!=1:continue
                raw=bytes(m.get_msgbuf());signed=raw[0]==253 and bool(raw[2]&1)
                valid=signed and hashlib.sha256(key+raw[:-6]).digest()[:6]==raw[-6:]
                if not m.base_mode&128 and (not require_signed or valid):return {'signed':signed,'valid_test_key':valid,'raw_hex':raw.hex()}
    raise RuntimeError('bootstrap heartbeat timeout signed='+str(require_signed))
try:
    log=(out/'sitl.log').open('wb')
    proc=subprocess.Popen([str(binary),'-I',str(instance),'--model','quad','--home=-35.363261,149.165230,584,0'],cwd=out,stdout=log,stderr=subprocess.STDOUT)
    primary=connect(base);secondary=connect(base+2)
    result['initial_primary']=wait_heartbeat(primary,out/'bootstrap-primary-down.bin')
    result['initial_secondary']=wait_heartbeat(secondary,out/'bootstrap-secondary-down.bin')
    enc=mav.MAVLink(None,srcSystem=255,srcComponent=189)
    stamp=int((time.time()-1420070400)*100000)
    packet=enc.setup_signing_encode(1,1,key,stamp).pack(enc)
    primary.sendall(packet);(out/'bootstrap-primary-up.bin').write_bytes(packet)
    result['configured_primary']=wait_heartbeat(primary,out/'bootstrap-primary-down.bin',True)
    result['configured_secondary']=wait_heartbeat(secondary,out/'bootstrap-secondary-down.bin',True)
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listener.bind(('127.0.0.1',base+1));listener.listen(1);listener.settimeout(80)
    for name in ('uplink','downlink'):files[name]=(out/(name+'.bin')).open('wb')
    (out/'ready.json').write_text(json.dumps({'proxy_port':base+1}));print('READY',base+1,flush=True)
    client,_=listener.accept();client.setblocking(False);secondary.setblocking(False)
    sample=bytes.fromhex(result['configured_secondary']['raw_hex'])
    altered=sample[:-1]+bytes([sample[-1]^1])
    injected=sample+sample+altered
    client.sendall(injected);files['downlink'].write(injected);files['downlink'].flush()
    (out/'injected.bin').write_bytes(injected)
    result['injected_sample_sha256']=hashlib.sha256(sample).hexdigest()
    result['injected_bad_sha256']=hashlib.sha256(altered).hexdigest()
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        r,_,_=select.select([client,secondary],[],[],.5)
        for source in r:
            chunk=source.recv(65536)
            if not chunk:result['closed_by']='client' if source is client else 'sitl';break
            name='uplink' if source is client else 'downlink';dest=secondary if source is client else client
            dest.sendall(chunk);files[name].write(chunk);files[name].flush()
        if result.get('closed_by'):break
    else:raise TimeoutError('relay deadline')
except Exception:result['errors'].append(traceback.format_exc())
finally:
    for sock in (client,listener,primary,secondary):
        if sock is not None:sock.close()
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
    if log:log.close()
    for f in files.values():f.close()
    result['capture_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.bin') if p.name!='eeprom.bin'}
    (out/'relay-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
if result['errors']:raise SystemExit(1)
