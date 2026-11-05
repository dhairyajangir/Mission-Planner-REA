"""Test MAVProxy forwarding while a disposable SITL vehicle reports armed."""
import hashlib,json,os,select,socket,subprocess,sys,time,traceback
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mav
case=os.environ['SITL_COMMAND_CASE'];instance=int(os.environ['SITL_COMMAND_INSTANCE'])
config={'mavproxy_forward_armed_block_retry':('false','true'),'mavproxy_forward_armed_allow_retry':('true','false')}
if case not in config or instance not in (179,180):raise ValueError('case/instance')
out=root/'sitl-evidence'/('command-ack-'+case);assert out.is_dir();base=5760+10*instance
env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(str(root/x) for x in ['research-tools/mavproxy-deps','sitl-evidence/python','ardupilot-mavproxy-source']);env['PYTHONUNBUFFERED']='1'
fwd,disarmed=config[case];settings='set requireexit true;set mavfwd '+fwd+';set mavfwd_disarmed '+disarmed+';set mavfwd;set mavfwd_disarmed'
result={'scope':'Disposable SITL only; synthetic forced arm, MAVProxy downstream read-only request, explicit disarm',
        'case':case,'source_commit':'8258c223d8da58f2db71a1c2eabb6834f35e8d8c','configured':{'mavfwd':fwd,'mavfwd_disarmed':disarmed},'errors':[]}
proxy=udp=control=controlraw=None;log=(out/'mavproxy.log').open('wb');before=(out/'udp-before.bin').open('wb');armed_before=(out/'udp-armed-before.bin').open('wb');after=(out/'udp-after.bin').open('wb')
def command(arm):
    m=control.mav.command_long_encode(1,1,mav.MAV_CMD_COMPONENT_ARM_DISARM,0,1 if arm else 0,21196,0,0,0,0,0)
    b=m.pack(control.mav);control.write(b)
    with (out/'control-uplink.bin').open('ab') as f:f.write(b)
def wait_hb(armed,timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        m=control.recv_match(type='HEARTBEAT',blocking=True,timeout=1)
        if m and m.get_srcSystem()==1 and bool(m.base_mode&128)==armed:return m
    raise TimeoutError('heartbeat armed='+str(armed))
try:
    udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',base+9));udp.setblocking(False)
    args=[sys.executable,'-m','MAVProxy.mavproxy','--master=tcp:127.0.0.1:'+str(base+1),'--out=udpout:127.0.0.1:'+str(base+9),
          '--no-state','--no-startup-scripts','--default-modules=param,wp','--cmd='+settings,'--state-basedir='+str(out)]
    result['argv']=args;proxy=subprocess.Popen(args,cwd=out,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,env=env)
    deadline=time.monotonic()+35;peer=None
    while time.monotonic()<deadline:
        if proxy.poll() is not None:raise RuntimeError('MAVProxy exited during startup')
        if select.select([udp],[],[],.1)[0]:data,peer=udp.recvfrom(65535);before.write(data)
        if peer and b'Received 1431 parameters' in (out/'mavproxy.log').read_bytes():break
    else:raise TimeoutError('MAVProxy startup')
    control=mavutil.mavlink_connection('tcp:127.0.0.1:'+str(base+2),source_system=254,source_component=188)
    controlraw=(out/'control-downlink.bin').open('wb');control.logfile_raw=controlraw
    result['initial_heartbeat']=wait_hb(False).to_dict()
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if b'EKF3 IMU0 MAG0 initial yaw alignment complete' in (out/'mavproxy.log').read_bytes():break
        time.sleep(.2)
    else:raise TimeoutError('estimator initialization')
    time.sleep(3);result['arm_attempted']=True;command(True)
    result['armed_heartbeat']=wait_hb(True).to_dict()
    # Wait for MAVProxy's output stream to carry an armed heartbeat before sending the probe.
    parser=mav.MAVLink(None);parser.robust_parsing=True;deadline=time.monotonic()+8;seen=False
    while time.monotonic()<deadline and not seen:
        if select.select([udp],[],[],.2)[0]:
            data,peer=udp.recvfrom(65535);armed_before.write(data)
            for b in data:
                m=parser.parse_char(bytes([b]))
                if m and m.get_type()=='HEARTBEAT' and m.get_srcSystem()==1 and m.base_mode&128:seen=True
    if not seen:raise RuntimeError('MAVProxy output did not show armed heartbeat')
    time.sleep(.5)
    while select.select([udp],[],[],0)[0]:data,peer=udp.recvfrom(65535);armed_before.write(data)
    enc=mav.MAVLink(None,srcSystem=211,srcComponent=77);request=enc.param_request_read_encode(1,1,b'LOG_DISARMED',-1).pack(enc)
    (out/'request.bin').write_bytes(request);udp.sendto(request,peer)
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        if select.select([udp],[],[],.1)[0]:data,_=udp.recvfrom(65535);after.write(data)
    command(False);result['final_heartbeat']=wait_hb(False).to_dict()
    proxy.stdin.write(b'exit\n');proxy.stdin.flush();proxy.stdin.close()
    try:result['proxy_exit']=proxy.wait(timeout=10)
    except subprocess.TimeoutExpired:proxy.terminate();result['proxy_exit']=proxy.wait(timeout=8);result['forced_terminate']=True
except Exception:result['errors'].append(traceback.format_exc())
finally:
    if control is not None:
        try:
            if result.get('arm_attempted') and 'final_heartbeat' not in result:command(False)
            control.close()
        except Exception:result['errors'].append(traceback.format_exc())
    if controlraw is not None:controlraw.close()
    if proxy is not None and proxy.poll() is None:
        proxy.terminate()
        try:proxy.wait(timeout=5)
        except subprocess.TimeoutExpired:proxy.kill();proxy.wait()
    if udp is not None:udp.close()
    log.close();before.close();armed_before.close();after.close()
    for n in ('mavproxy.log','udp-before.bin','udp-armed-before.bin','udp-after.bin','request.bin','control-uplink.bin','control-downlink.bin'):
        p=out/n
        if p.exists():result.setdefault('artifacts',{})[n]=hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'mavproxy-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if result['errors']:raise SystemExit(1)
