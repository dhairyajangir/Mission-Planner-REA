# Test-only modified Mission Planner copy, local file spool and disposable SITL.
import clr
import System
clr.AddReference('FileSpoolSerial')
from MissionPlannerTest import FileSpoolSerial
result_path = System.Environment.GetEnvironmentVariable('MP_INTEGRATED_RESULT')
spool_path = System.Environment.GetEnvironmentVariable('MP_SPOOL_DIR')
stop_path = System.Environment.GetEnvironmentVariable('MP_STOP_PATH')
lines = ['scope=modified app, plugin-disabled, file-spool transport, disposable local SITL']
try:
    MAV.BaseStream = FileSpoolSerial(spool_path)
    MainV2.doConnect(MAV, 'preset', '0', False, False)
    if not MAV.BaseStream.IsOpen: raise Exception('connection did not open')
    Script.Sleep(12000)
    armed = MAV.doARM(True, True)
    lines.append('arm_return=' + str(armed))
    for i in range(20):
        Script.Sleep(500)
        if MAV.MAV.cs.armed: break
    lines.append('armed_state=' + str(MAV.MAV.cs.armed))
    if not armed or not MAV.MAV.cs.armed: raise Exception('simulator did not report armed')
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
    for i in range(540):
        if System.IO.File.Exists(stop_path): break
        Script.Sleep(1000)
    if MAV.BaseStream.IsOpen:
        lines.append('disarm_return=' + str(MAV.doARM(False, True)))
        Script.Sleep(1500)
        lines.append('final_armed=' + str(MAV.MAV.cs.armed))
        MAV.Close()
except Exception as ex:
    lines.append('error=' + str(ex))
finally:
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
