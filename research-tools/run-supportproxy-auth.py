from pathlib import Path
import subprocess
root = Path(__file__).resolve().parent.parent
out = root/'supportproxy-evidence/auth-tests'
out.mkdir(parents=True, exist_ok=False)
base = '/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project'
dep = base + '/supportproxy-deps'
repo = base + '/supportproxy-source'
shell = 'export PATH="' + dep + '/python-bin:$PATH"; exec /usr/bin/python3 -m pytest -q "' + repo + '/tests/test_authentication.py" --basetemp="' + base + '/supportproxy-evidence/auth-tests/tmp"'
args = ['wsl.exe','-e','env', 'PYTHONPATH='+dep+'/python:'+dep+'/root/usr/lib/python3/dist-packages:'+repo+'/modules/mavlink',
        'LD_LIBRARY_PATH='+dep+'/root/usr/lib/x86_64-linux-gnu','MDEF='+repo+'/modules/mavlink/message_definitions',
        'sh','-c',shell]
p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
(out/'pytest.log').write_bytes(p.stdout)
(out/'exit.txt').write_text(str(p.returncode))
print(p.stdout.decode(errors='replace')[-6000:])
print('EXIT', p.returncode)
