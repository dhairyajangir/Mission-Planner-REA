# Runs within the test-only, data-path-redirected Mission Planner application.
# FileSpoolSerial uses workspace files; a separate relay reaches local SITL.
import clr
import System
clr.AddReference('FileSpoolSerial')
from MissionPlannerTest import FileSpoolSerial

result_path = System.Environment.GetEnvironmentVariable('MP_INTEGRATED_RESULT')
spool_path = System.Environment.GetEnvironmentVariable('MP_SPOOL_DIR')
lines = ['scope=isolated app, plugin-disabled, file-spool transport, local SITL']
try:
    MAV.BaseStream = FileSpoolSerial(spool_path)
    MainV2.doConnect(MAV, 'preset', '0', False, False)
    lines.append('open=' + str(MAV.BaseStream.IsOpen))
    lines.append('system=' + str(MAV.sysidcurrent))
    lines.append('component=' + str(MAV.compidcurrent))
    if MAV.BaseStream.IsOpen:
        lines.append('mission_count=' + str(MAV.getWPCount()))
        Script.Sleep(5000)
        lines.append('state_lat=' + str(MAV.MAV.cs.lat))
        lines.append('state_lng=' + str(MAV.MAV.cs.lng))
        MAV.Close()
except Exception as ex:
    lines.append('error=' + str(ex))
finally:
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
