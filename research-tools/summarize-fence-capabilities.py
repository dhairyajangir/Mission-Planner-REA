"""Validate in-memory fence and rally guard evidence."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/fence-capability-synthetic'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
lines = (out / 'probe.log').read_text(encoding='utf8').splitlines()
expected = ['FENCE_UPLOAD=Fence mission items not supported, please use legacy geofence BYTES=0',
            'FENCE_DOWNLOAD=Fence mission items not supported, please use legacy geofence BYTES=0',
            'RALLY_UPLOAD=Mission type only supported under mavlink2 BYTES=0',
            'RALLY_DOWNLOAD=Mission type only supported under mavlink2 BYTES=0']
assert lines == expected and (out / 'probe-initial.log').read_text(encoding='utf8').splitlines() == expected
assert (out / 'capture.bin').read_bytes() == b''
summary = {'scope': 'Synthetic in-memory transport with zero capabilities and MAVLink 1; no vehicle or UI',
           'lines': lines, 'capture_sha256': sha(out / 'capture.bin'), 'probe_log_sha256': sha(out / 'probe.log'),
           'probe_source_sha256': sha(out / 'probe-source.cs'), 'transport_source_sha256': sha(out / 'transport-source.cs'),
           'probe_exe_sha256': sha(out / 'probe.exe'), 'library_sha256': sha(root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll')}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Four guard cases rejected with zero captured output bytes')
