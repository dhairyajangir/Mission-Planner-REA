# Test-only modified Mission Planner copy connected to local SITL via file spool.
import clr
import System
clr.AddReference('FileSpoolSerial')
from MissionPlannerTest import FileSpoolSerial

result_path = System.Environment.GetEnvironmentVariable('MP_INTEGRATED_RESULT')
spool_path = System.Environment.GetEnvironmentVariable('MP_SPOOL_DIR')
lines = ['scope=modified app, plugin-disabled, file-spool transport, local SITL']
try:
    MAV.BaseStream = FileSpoolSerial(spool_path)
    MainV2.doConnect(MAV, 'preset', '0', False, False)
    lines.append('open=' + str(MAV.BaseStream.IsOpen))
    if not MAV.BaseStream.IsOpen:
        raise Exception('connection did not open')
    Script.Sleep(15000)
    parameters = MAV.getParamListMavftp(System.Byte(MAV.sysidcurrent), System.Byte(MAV.compidcurrent))
    lines.append('params_received=' + str(parameters.TotalReceived))
    lines.append('params_reported=' + str(parameters.TotalReported))
    lines.append('initial_value=' + str(MAV.GetParam('LOG_DISARMED')))
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
    Script.Sleep(210000)
    after = MAV.GetParam('LOG_DISARMED')
    lines.append('readback=' + str(after))
    if after != 0:
        lines.append('restore_ok=' + str(MAV.setParam('LOG_DISARMED', 0)))
        lines.append('restored_value=' + str(MAV.GetParam('LOG_DISARMED')))
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
    Script.Sleep(10000)
    MAV.Close()
except Exception as ex:
    lines.append('error=' + str(ex))
finally:
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
