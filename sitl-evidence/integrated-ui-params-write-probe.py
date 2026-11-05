# Test-only modified Mission Planner, local SITL, and file-spool transport.
import clr
import System
clr.AddReference('FileSpoolSerial')
from MissionPlannerTest import FileSpoolSerial

result_path = System.Environment.GetEnvironmentVariable('MP_INTEGRATED_RESULT')
spool_path = System.Environment.GetEnvironmentVariable('MP_SPOOL_DIR')
marker_path = System.Environment.GetEnvironmentVariable('MP_READBACK_MARKER')
lines = ['scope=modified app, plugin-disabled, file-spool transport, disposable local SITL']
try:
    MAV.BaseStream = FileSpoolSerial(spool_path)
    MainV2.doConnect(MAV, 'preset', '0', False, False)
    lines.append('open=' + str(MAV.BaseStream.IsOpen))
    if not MAV.BaseStream.IsOpen:
        raise Exception('connection did not open')
    Script.Sleep(15000)
    params = MAV.getParamListMavftp(System.Byte(MAV.sysidcurrent), System.Byte(MAV.compidcurrent))
    lines.append('params_received=' + str(params.TotalReceived))
    lines.append('params_reported=' + str(params.TotalReported))
    lines.append('initial_value=' + str(MAV.GetParam('LOG_DISARMED')))
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
    for iteration in range(600):
        if System.IO.File.Exists(marker_path):
            break
        Script.Sleep(1000)
    else:
        raise Exception('readback marker not received before timeout')
    after = MAV.GetParam('LOG_DISARMED')
    lines.append('readback=' + str(after))
    if after != 0:
        lines.append('restore_ok=' + str(MAV.setParam('LOG_DISARMED', 0)))
        lines.append('restored_value=' + str(MAV.GetParam('LOG_DISARMED')))
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
    Script.Sleep(5000)
    MAV.Close()
except Exception as ex:
    lines.append('error=' + str(ex))
finally:
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
