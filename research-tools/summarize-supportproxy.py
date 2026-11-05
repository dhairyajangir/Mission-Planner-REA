from pathlib import Path
import hashlib, json, subprocess
root = Path(__file__).resolve().parent.parent
repo = root/'supportproxy-source'; evidence = root/'supportproxy-evidence'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def git(path, *args): return subprocess.check_output(['git','-C',str(path),*args], text=True).strip()
revisions = {'supportproxy':git(repo,'rev-parse','HEAD'), 'mavlink':git(repo/'modules/mavlink','rev-parse','HEAD'),
             'pymavlink':git(repo/'modules/mavlink/pymavlink','rev-parse','HEAD')}
assert revisions == {'supportproxy':'21ca25286b2a0bcc25228e4d6bc20c5438abdcce', 'mavlink':'a23652e3c7d1d7a94b1c2d354a13ce4858cd0996',
                     'pymavlink':'19880422d451de4daba3fd96781076afb1cb889c'}
for f in ('regen_headers.sh','git-version.sh'):
    assert git(repo,'hash-object','--no-filters',f) == git(repo,'rev-parse','HEAD:'+f)
logs = {}
for folder, phrase in [('auth-tests','13 passed'),('local-network-tests','8 passed')]:
    path = evidence/folder
    assert (path/'exit.txt').read_text().strip() == '0' and phrase in (path/'pytest.log').read_text()
    logs[folder] = {'log_sha256':sha(path/'pytest.log'),'expected_summary':phrase,'exit':0}
source_names = ['README.md','supportproxy.cpp','mavlink.cpp','keydb_lib.py','tests/test_connections.py','tests/test_authentication.py']
result = {'scope':'source-built SupportProxy; local ephemeral databases and synthetic loopback connections',
          'revisions':revisions,'binary_sha256':sha(repo/'supportproxy'),
          'source_sha256':{n:sha(repo/n) for n in source_names},
          'interposer_source_sha256':sha(root/'research-tools/supportproxy-loopback-bind.c'),
          'interposer_binary_sha256':sha(root/'supportproxy-deps/loopback-bind.so'), 'tests':logs}
(evidence/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
