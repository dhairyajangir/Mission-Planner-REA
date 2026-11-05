"""Run pinned MAVProxy source against disposable local Copter SITL."""
import hashlib,json,os,select,socket,subprocess,sys,time,traceback
from pathlib import Path
root=Path(__file__).resolve().parent.parent;out=root/'sitl-evidence/mavproxy-sitl-smoke-3';out.mkdir(exist_ok=False)
repo=root/'ardupilot-mavproxy-source';binary=root/'sitl-evidence/archive-built/arducopter'
result={'scope':'Pinned MAVProxy source, local disposable disarmed Copter SITL, no physical vehicle',
        'source_commit':'8258c223d8da58f2db71a1c2eabb6834f35e8d8c','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'commands':[],'errors':[]}
proc=proxy=udp=None;log=(out/'sitl.log').open('wb');proxylog=(out/'mavproxy.log').open('wb');capture=(out/'forwarded.bin').open('wb')
try:
    udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',14599));udp.setblocking(False)
    proc=subprocess.Popen([str(binary),'-I','180','--model','quad','--home=-35.363261,149.165230,584,0'],cwd=out,stdout=log,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+30
    while True:
        if proc.poll() is not None:raise RuntimeError('simulator exited')
        if b'SERIAL0 on TCP port 7560' in (out/'sitl.log').read_bytes():break
        if time.monotonic()>deadline:raise TimeoutError('SITL startup')
        time.sleep(.2)
    env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(str(root/x) for x in ['research-tools/mavproxy-deps','sitl-evidence/python','ardupilot-mavproxy-source'])
    env['PYTHONUNBUFFERED']='1'
    args=[sys.executable,'-m','MAVProxy.mavproxy','--master=tcp:127.0.0.1:7560','--out=udpout:127.0.0.1:14599',
          '--no-state','--no-startup-scripts','--default-modules=param,wp','--cmd=set requireexit true','--state-basedir='+str(out)]
    result['argv']=args
    proxy=subprocess.Popen(args,cwd=out,stdin=subprocess.PIPE,stdout=proxylog,stderr=subprocess.STDOUT,env=env)
    start=time.monotonic();sent=False;packets=0
    while time.monotonic()-start<24:
        if proxy.poll() is not None:break
        if select.select([udp],[],[],.2)[0]:
            data,_=udp.recvfrom(65535);capture.write(data);capture.flush();packets+=1
        if not sent and time.monotonic()-start>=15:
            for cmd in ('param show LOG_DISARMED','wp list'):
                proxy.stdin.write((cmd+'\n').encode());proxy.stdin.flush();result['commands'].append(cmd)
            sent=True
    result['forwarded_datagrams']=packets
    if proxy.poll() is None:
        proxy.stdin.write(b'exit\n');proxy.stdin.flush();proxy.stdin.close();result['commands'].append('exit');result['stdin_closed']=True
        try:result['proxy_exit']=proxy.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proxy.terminate();result['proxy_exit']=proxy.wait(timeout=8);result['forced_terminate']=True
    else:result['proxy_exit']=proxy.returncode
except Exception:result['errors'].append(traceback.format_exc())
finally:
    if proxy is not None and proxy.poll() is None:
        proxy.terminate()
        try:proxy.wait(timeout=5)
        except subprocess.TimeoutExpired:proxy.kill();proxy.wait()
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
    if udp is not None:udp.close()
    log.close();proxylog.close();capture.close()
    result['artifacts']={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['sitl.log','mavproxy.log','forwarded.bin']}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
if result['errors']:raise SystemExit(1)
