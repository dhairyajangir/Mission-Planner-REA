import pathlib, shutil, subprocess, sys
root = pathlib.Path(__file__).resolve().parent.parent
case, port = sys.argv[1:]
assert case in ('plane_guided_drop_one', 'plane_guided_drop_all')
assert port in ('7551', '7561')
out = root / ('sitl-evidence/command-ack-' + case)
exe = root / 'mission-planner-portable/PlaneGuidedLossProbe.exe'
for source, name in ((exe, 'probe.exe'), (root/'research-tools/PlaneGuidedLossProbe.cs', 'probe-source.cs'),
                     (root/'sitl-evidence/command-ack-relay.py', 'relay-source.py')):
    shutil.copy2(source, out/name)
proc = subprocess.run([str(exe), port], cwd=exe.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=100)
(out/'probe.log').write_bytes(proc.stdout)
(out/'probe-exit.txt').write_text(str(proc.returncode))
print(proc.stdout.decode(errors='replace')[-2500:])
print('EXIT', proc.returncode)
sys.exit(proc.returncode)
