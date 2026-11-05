"""Derive a separate local UI write test from the existing mission probe."""
from pathlib import Path

base = Path(__file__).resolve().parent
probe = (base / 'integrated-ui-mission-probe.py').read_text()
old = '    Script.Sleep(120000)\n    MAV.Close()'
new = '''    Script.Sleep(140000)
    returned = MAV.getWP(System.UInt16(1))
    lines.append('readback_lat=' + str(returned.lat))
    lines.append('readback_lng=' + str(returned.lng))
    lines.append('readback_alt=' + str(returned.alt))
    System.IO.File.WriteAllText(result_path, '\\n'.join(lines) + '\\n')
    Script.Sleep(30000)
    MAV.Close()'''
if old not in probe:
    raise ValueError('expected mission probe block not found')
(base / 'integrated-ui-write-probe.py').write_text(probe.replace(old, new))
launcher = (base / 'launch-integrated-mission-ui.py').read_text()
launcher = launcher.replace('integrated-ui-mission', 'integrated-ui-write')
(base / 'launch-integrated-write-ui.py').write_text(launcher)
