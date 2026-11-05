"""Probe downstream parameter-request forwarding through pinned MAVProxy source."""
import hashlib,json,os,select,socket,subprocess,sys,time,traceback
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega as mav
case=os.environ['SITL_COMMAND_CASE'];instance=int(os.environ['SITL_COMMAND_INSTANCE'])
config={'mavproxy_forward_default':('true','true'),'mavproxy_forward_disabled':('false','false'),'mavproxy_forward_disarmed':('false','true')}
if case not in config or instance not in (178,179,180):raise ValueError('case/instance')
out=root/'sitl-evidence'/('command-ack-'+case);assert out.is_dir();base=5760+10*instance
env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(str(root/x) for x in ['research-tools/mavproxy-deps','sitl-evidence/python','ardupilot-mavproxy-source']);env['PYTHONUNBUFFERED']='1'
fwd,disarmed=config[case]
settings='set requireexit true;set mavfwd '+fwd+';set mavfwd_disarmed '+disarmed+';set mavfwd;set mavfwd_disarmed'
result={'scope':'Pinned MAVProxy source; synthetic downstream parameter request; disposable disarmed Copter SITL',
        'case':case,'source_commit':'8258c223d8da58f2db71a1c2eabb6834f35e8d8c','configured':{'mavfwd':fwd,'mavfwd_disarmed':disarmed},'errors':[]}
proxy=udp=None;log=(out/'mavproxy.log').open('wb');before=(out/'udp-before.bin').open('wb');after=(out/'udp-after.bin').open('wb')
try:
    udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',base+9));udp.setblocking(False)
    args=[sys.executable,'-m','MAVProxy.mavproxy','--master=tcp:127.0.0.1:'+str(base+1),'--out=udpout:127.0.0.1:'+str(base+9),
          '--no-state','--no-startup-scripts','--default-modules=param,wp','--cmd='+settings,'--state-basedir='+str(out)]
    result['argv']=args;proxy=subprocess.Popen(args,cwd=out,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,env=env)
    deadline=time.monotonic()+35;peer=None
    while time.monotonic()<deadline:
        if proxy.poll() is not None:raise RuntimeError('MAVProxy exited during startup')
        if select.select([udp],[],[],.1)[0]:
            data,peer=udp.recvfrom(65535);before.write(data)
        if peer and b'Received 1431 parameters' in (out/'mavproxy.log').read_bytes():break
    else:raise TimeoutError('MAVProxy startup')
    # Drain queued broadcasts before issuing the unique external request.
    while select.select([udp],[],[],0)[0]:
        data,peer=udp.recvfrom(65535);before.write(data)
    enc=mav.MAVLink(None,srcSystem=211,srcComponent=77)
    request=enc.param_request_read_encode(1,1,b'LOG_DISARMED',-1).pack(enc)
    (out/'request.bin').write_bytes(request);udp.sendto(request,peer);result['peer']=[peer[0],peer[1]]
    deadline=time.monotonic()+3;datagrams=0
    while time.monotonic()<deadline:
        if select.select([udp],[],[],.1)[0]:
            data,_=udp.recvfrom(65535);after.write(data);datagrams+=1
    result['post_request_datagrams']=datagrams
    proxy.stdin.write(b'exit\n');proxy.stdin.flush();proxy.stdin.close()
    try:result['proxy_exit']=proxy.wait(timeout=10)
    except subprocess.TimeoutExpired:proxy.terminate();result['proxy_exit']=proxy.wait(timeout=8);result['forced_terminate']=True
except Exception:result['errors'].append(traceback.format_exc())
finally:
    if proxy is not None and proxy.poll() is None:
        proxy.terminate()
        try:proxy.wait(timeout=5)
        except subprocess.TimeoutExpired:proxy.kill();proxy.wait()
    if udp is not None:udp.close()
    log.close();before.close();after.close()
    for n in ('mavproxy.log','udp-before.bin','udp-after.bin','request.bin'):
        p=out/n
        if p.exists():result.setdefault('artifacts',{})[n]=hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'mavproxy-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if result['errors']:raise SystemExit(1)
