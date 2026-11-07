from pathlib import Path
import subprocess
from env_paths import SUPPORTPROXY_BIND_SHIM, wsl_path
root = Path(__file__).resolve().parent.parent
out = root/'supportproxy-evidence/local-network-tests'
out.mkdir(parents=True, exist_ok=False)
base = wsl_path(root)
dep, repo = base+'/supportproxy-deps', base+'/supportproxy-source'
test = repo+'/tests/test_connections.py'
targets = [test+'::TestUDPConnections', test+'::TestTCPConnections', test+'::TestMixedConnections']
shell = 'export PATH="'+dep+'/python-bin:$PATH"; exec /usr/bin/python3 -m pytest -q '+ ' '.join('"'+t+'"' for t in targets) + ' --basetemp="'+base+'/supportproxy-evidence/local-network-tests/tmp"'
args = ['wsl.exe','-e','env','PYTHONPATH='+dep+'/python:'+dep+'/root/usr/lib/python3/dist-packages:'+repo+'/modules/mavlink',
        'LD_LIBRARY_PATH='+dep+'/root/usr/lib/x86_64-linux-gnu',
        'LD_PRELOAD='+wsl_path(SUPPORTPROXY_BIND_SHIM),
        'MDEF='+repo+'/modules/mavlink/message_definitions','sh','-c',shell]
p = subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
(out/'pytest.log').write_bytes(p.stdout)
(out/'exit.txt').write_text(str(p.returncode))
print(p.stdout.decode(errors='replace')[-6000:]); print('EXIT', p.returncode)
