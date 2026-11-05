# Executed by Mission Planner's built-in IronPython script runner. This is a
# localhost-only test against a disposable SITL process; no flight commands.
import clr
import System
from MissionPlanner.Comms import TcpSerial

result_path = System.Environment.GetEnvironmentVariable('MP_INTEGRATED_RESULT')
lines = ['scope=isolated Mission Planner data-path test copy, local SITL']
try:
    stream = TcpSerial()
    stream.Host = '127.0.0.1'
    stream.Port = '6220'
    MAV.BaseStream = stream
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
