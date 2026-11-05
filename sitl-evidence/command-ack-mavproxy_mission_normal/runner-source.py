"""Use MAVProxy to upload a disposable mission; independently read via SERIAL1."""
import hashlib,json,os,shlex,subprocess,sys,time,traceback
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink import mavutil
case=os.environ['SITL_COMMAND_CASE'];instance=int(os.environ['SITL_COMMAND_INSTANCE'])
if case not in ('mavproxy_mission_normal','mavproxy_mission_drop_ack') or instance not in (179,180):raise ValueError('invalid case')
out=root/'sitl-evidence'/('command-ack-'+case);assert out.is_dir()
fixture=out/'input.waypoints'
fixture.write_text('QGC WPL 110\n0\t1\t0\t16\t0\t0\t0\t0\t-35.363261\t149.165230\t584\t1\n1\t0\t3\t16\t2\t0\t0\t0\t-35.362500\t149.166000\t25\t1\n')
env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(str(root/x) for x in ['research-tools/mavproxy-deps','sitl-evidence/python','ardupilot-mavproxy-source']);env['PYTHONUNBUFFERED']='1'
port=5760+10*instance
result={'case':case,'scope':'Pinned MAVProxy mission upload and separate SERIAL1 client; disposable disarmed Copter SITL',
        'source_commit':'8258c223d8da58f2db71a1c2eabb6834f35e8d8c','commands':[],'errors':[]}
proxy=client=raw=None;log=(out/'mavproxy.log').open('wb')
try:
    args=[sys.executable,'-m','MAVProxy.mavproxy','--master=tcp:127.0.0.1:'+str(port+1),
          '--no-state','--no-startup-scripts','--default-modules=param,wp','--cmd=set requireexit true','--state-basedir='+str(out)]
    result['argv']=args;proxy=subprocess.Popen(args,cwd=out,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,env=env)
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if proxy.poll() is not None:raise RuntimeError('MAVProxy exited before startup')
        if b'Received 1431 parameters' in (out/'mavproxy.log').read_bytes():break
        time.sleep(.25)
    else:raise TimeoutError('MAVProxy parameter startup')
    cmd='wp load '+shlex.quote(str(fixture));proxy.stdin.write((cmd+'\n').encode());proxy.stdin.flush();result['commands'].append(cmd)
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        if b'Sent all 2 waypoints' in (out/'mavproxy.log').read_bytes():break
        if proxy.poll() is not None:raise RuntimeError('MAVProxy exited during upload')
        time.sleep(.2)
    else:raise TimeoutError('MAVProxy did not report sending mission')
    time.sleep(2)
    client=mavutil.mavlink_connection('tcp:127.0.0.1:'+str(port+2),source_system=254,source_component=188)
    raw=(out/'independent-downlink.bin').open('wb');client.logfile_raw=raw
    heartbeat=client.wait_heartbeat(timeout=10)
    if heartbeat is None or heartbeat.base_mode&128:raise RuntimeError('no disarmed heartbeat')
    result['independent_heartbeat']=heartbeat.to_dict()
    client.mav.mission_request_list_send(1,1,0)
    count=client.recv_match(type='MISSION_COUNT',blocking=True,timeout=10)
    if count is None:raise TimeoutError('mission count')
    result['mission_count']=count.to_dict()
    result['readback']=[]
    for seq in range(count.count):
        client.mav.mission_request_int_send(1,1,seq,0)
        item=client.recv_match(type='MISSION_ITEM_INT',blocking=True,timeout=10)
        if item is None:raise TimeoutError('mission item '+str(seq))
        result['readback'].append(item.to_dict())
    proxy.stdin.write(b'exit\n');proxy.stdin.flush();proxy.stdin.close();result['commands'].append('exit')
    try:result['proxy_exit']=proxy.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proxy.terminate();result['proxy_exit']=proxy.wait(timeout=8);result['forced_terminate']=True
except Exception:result['errors'].append(traceback.format_exc())
finally:
    if client is not None:client.close()
    if raw is not None:raw.close()
    if proxy is not None and proxy.poll() is None:
        proxy.terminate()
        try:proxy.wait(timeout=5)
        except subprocess.TimeoutExpired:proxy.kill();proxy.wait()
    log.close()
    for n in ('input.waypoints','mavproxy.log','independent-downlink.bin'):
        p=out/n
        if p.exists():result.setdefault('artifacts',{})[n]=hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'mavproxy-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
if result['errors']:raise SystemExit(1)
