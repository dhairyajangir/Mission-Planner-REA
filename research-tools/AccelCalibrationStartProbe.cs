// Calls the same library command as the accelerometer calibration screen.
// Disposable, disarmed SITL only; intentionally does not acknowledge a position.
using System;
using System.Text;
using MissionPlanner;
using MissionPlanner.Comms;
public static class AccelCalibrationStartProbe
{
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            var initialDeadline = DateTime.UtcNow.AddSeconds(8);
            bool disarmed = false;
            while (DateTime.UtcNow < initialDeadline) {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                if ((hb.base_mode & 128) != 0) throw new Exception("armed");
                disarmed = true; break;
            }
            if (!disarmed) throw new Exception("no disarmed heartbeat");
            Console.WriteLine("INITIAL_ARMED=False");
            bool accepted = port.doCommand(1, 1, MAVLink.MAV_CMD.PREFLIGHT_CALIBRATION, 0, 0, 0, 0, 1, 0, 0, true);
            Console.WriteLine("PREFLIGHT_CALIBRATION_RETURN=" + accepted);
            var end = DateTime.UtcNow.AddSeconds(12);
            int positions = 0;
            while (DateTime.UtcNow < end) {
                var p = port.readPacket();
                if (p.sysid != 1 || p.compid != 1) continue;
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT) {
                    var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                    if ((hb.base_mode & 128) != 0) throw new Exception("armed during probe");
                } else if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.COMMAND_LONG) {
                    var cmd = p.ToStructure<MAVLink.mavlink_command_long_t>();
                    if (cmd.command == (ushort)MAVLink.MAV_CMD.ACCELCAL_VEHICLE_POS) {
                        Console.WriteLine("POSITION_REQUEST=" + cmd.param1);
                        positions++;
                    }
                } else if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.STATUSTEXT) {
                    Console.WriteLine("STATUS=" + Encoding.ASCII.GetString(p.ToStructure<MAVLink.mavlink_statustext_t>().text).TrimEnd('\0'));
                }
            }
            Console.WriteLine("POSITION_REQUEST_COUNT=" + positions);
            return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
