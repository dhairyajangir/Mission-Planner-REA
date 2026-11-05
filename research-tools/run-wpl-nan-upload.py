from pathlib import Path
import shutil, subprocess, sys
root = Path(__file__).resolve().parent.parent
form, port = sys.argv[1:]
assert (form,port) in (('int','7551'),('float','7561'),('float_retry','7561'))
out = root/('sitl-evidence/command-ack-wpl_nan_'+form)
exe = root/'mission-planner-portable/WaypointNanUploadProbe.exe'
fixture = root/'sitl-evidence/waypoint-import-edges/nonfinite.waypoints'
for source, name in [(exe,'probe.exe'),(root/'research-tools/WaypointNanUploadProbe.cs','probe-source.cs'),
                     (root/'sitl-evidence/command-ack-relay.py','relay-source.py'),(fixture,'input.waypoints')]:
    shutil.copy2(source,out/name)
p = subprocess.run([str(exe),port,str(out/'input.waypoints'),form],cwd=exe.parent,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=100)
(out/'probe.log').write_bytes(p.stdout); (out/'probe-exit.txt').write_text(str(p.returncode))
print(p.stdout.decode(errors='replace')[-3500:]); print('EXIT',p.returncode)
sys.exit(p.returncode)
