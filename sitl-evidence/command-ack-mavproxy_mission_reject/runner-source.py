"""Upload valid then invalid missions to disposable SITL; independent readback."""
import hashlib,json,os,subprocess,sys,time,traceback
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink import mavutil
case='mavproxy_mission_reject';out=root/'sitl-evidence'/('command-ack-'+case);assert out.is_dir()
home='0\t1\t0\t16\t0\t0\t0\t0\t-35.363261\t149.165230\t584\t1\n'
valid='1\t0\t3\t16\t2\t0\t0\t0\t-35.362500\t149.166000\t25\t1\n'
invalid='1\t0\t3\t65535\t2\t0\t0\t0\t-35.362600\t149.166100\t30\t1\n'
(out/'baseline.waypoints').write_text('QGC WPL 110\n'+home+valid)
(out/'invalid.waypoints').write_text('QGC WPL 110\n'+home+invalid)
env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(str(root/x) for x in ['research-tools/mavproxy-deps','sitl-evidence/python','ardupilot-mavproxy-source']);env['PYTHONUNBUFFERED']='1'
result={'case':case,'scope':'MAVProxy valid mission then invalid replacement; disposable disarmed Copter SITL',
        'source_commit':'8258c223d8da58f2db71a1c2eabb6834f35e8d8c','commands':[],'phases':{},'errors':[]}
proxy=client=raw=None;log=(out/'mavproxy.log').open('wb')
def send(command):
    proxy.stdin.write((command+'\n').encode());proxy.stdin.flush();result['commands'].append(command)
def wait_log(text,count,timeout=20):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        if (out/'mavproxy.log').read_bytes().count(text.encode())>=count:return
        if proxy.poll() is not None:raise RuntimeError('MAVProxy exited early')
        time.sleep(.2)
    raise TimeoutError('log: '+text)
def readback(phase):
    global raw
    raw=(out/(phase+'-downlink.bin')).open('wb');client.logfile_raw=raw
    client.mav.mission_request_list_send(1,1,0)
    count=client.recv_match(type='MISSION_COUNT',blocking=True,timeout=8)
    if count is None:raise TimeoutError(phase+' count')
    entry={'count':count.to_dict(),'items':[]}
    for seq in range(count.count):
        client.mav.mission_request_int_send(1,1,seq,0)
        m=client.recv_match(type=['MISSION_ITEM_INT','MISSION_ACK'],blocking=True,timeout=8)
        if m is None:entry['timeout_at']=seq;break
        if m.get_type()=='MISSION_ACK':entry['error_at']=seq;entry['ack']=m.to_dict();break
        entry['items'].append(m.to_dict())
    raw.close();raw=None;client.logfile_raw=None
    result['phases'][phase]=entry
try:
    args=[sys.executable,'-m','MAVProxy.mavproxy','--master=tcp:127.0.0.1:7561',
          '--no-state','--no-startup-scripts','--default-modules=param,wp','--cmd=set requireexit true','--state-basedir='+str(out)]
    result['argv']=args;proxy=subprocess.Popen(args,cwd=out,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,env=env)
    wait_log('Received 1431 parameters',1,35)
    send('wp load baseline.waypoints');wait_log('Sent all 2 waypoints',1);time.sleep(2)
    client=mavutil.mavlink_connection('tcp:127.0.0.1:7562',source_system=254,source_component=188)
    heartbeat=client.wait_heartbeat(timeout=10)
    if heartbeat is None or heartbeat.base_mode&128:raise RuntimeError('no disarmed heartbeat')
    result['independent_heartbeat']=heartbeat.to_dict();readback('baseline')
    send('wp load invalid.waypoints');wait_log('Sent all 2 waypoints',2);time.sleep(2);readback('after_invalid')
    send('exit');proxy.stdin.close()
    try:result['proxy_exit']=proxy.wait(timeout=10)
    except subprocess.TimeoutExpired:proxy.terminate();result['proxy_exit']=proxy.wait(timeout=8);result['forced_terminate']=True
except Exception:result['errors'].append(traceback.format_exc())
finally:
    if client is not None:client.close()
    if raw is not None:raw.close()
    if proxy is not None and proxy.poll() is None:
        proxy.terminate()
        try:proxy.wait(timeout=5)
        except subprocess.TimeoutExpired:proxy.kill();proxy.wait()
    log.close()
    for n in ('baseline.waypoints','invalid.waypoints','mavproxy.log','baseline-downlink.bin','after_invalid-downlink.bin'):
        p=out/n
        if p.exists():result.setdefault('artifacts',{})[n]=hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'mavproxy-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if result['errors']:raise SystemExit(1)
