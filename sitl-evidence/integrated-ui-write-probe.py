# Runs within the modified Mission Planner test copy against local SITL only.
import clr
import System
clr.AddReference('FileSpoolSerial')
from MissionPlannerTest import FileSpoolSerial
from MissionPlanner.Utilities import Locationwp

result_path = System.Environment.GetEnvironmentVariable('MP_INTEGRATED_RESULT')
spool_path = System.Environment.GetEnvironmentVariable('MP_SPOOL_DIR')
lines = ['scope=modified app, plugin-disabled, file-spool transport, local SITL']
try:
    MAV.BaseStream = FileSpoolSerial(spool_path)
    MainV2.doConnect(MAV, 'preset', '0', False, False)
    lines.append('open=' + str(MAV.BaseStream.IsOpen))
    if not MAV.BaseStream.IsOpen:
        raise Exception('connection did not open')
    stream_type = System.Type.GetType('MAVLink+MAV_DATA_STREAM, MAVLink', True)
    frame_type = System.Type.GetType('MAVLink+MAV_FRAME, MAVLink', True)
    frame = System.Enum.ToObject(frame_type, 3)
    MAV.requestDatastream(System.Enum.ToObject(stream_type, 0), System.Byte(4))
    Script.Sleep(15000)
    home = Locationwp().Set(-35.363261, 149.165230, 0, System.UInt16(16))
    waypoint = Locationwp().Set(-35.363, 149.1655, 20, System.UInt16(16))
    MAV.setWPTotal(System.UInt16(2))
    first = MAV.setWP(home, System.UInt16(0), frame, System.Byte(0), System.Byte(1), True)
    second = MAV.setWP(waypoint, System.UInt16(1), frame, System.Byte(0), System.Byte(1), True)
    lines.append('upload_results=' + str(first) + ',' + str(second))
    lines.append('mission_count=' + str(MAV.getWPCount()))
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
    Script.Sleep(140000)
    returned = MAV.getWP(System.UInt16(1))
    lines.append('readback_lat=' + str(returned.lat))
    lines.append('readback_lng=' + str(returned.lng))
    lines.append('readback_alt=' + str(returned.alt))
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
    Script.Sleep(30000)
    MAV.Close()
except Exception as ex:
    lines.append('error=' + str(ex))
finally:
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
