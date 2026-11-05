// Full accelerometer workflow using the disposable SITL calibration model.
using System;
using System.Text;
using MissionPlanner;
using MissionPlanner.Comms;
public static class AccelCalibrationFullProbe
{
    static void Servo(MAVLinkInterface port, int channel, int pwm) {
        bool ok = port.doCommand(1, 1, MAVLink.MAV_CMD.DO_SET_SERVO, channel, pwm, 0, 0, 0, 0, 0, true);
        Console.WriteLine("SERVO=" + channel + ":" + pwm + " ACCEPTED=" + ok);
        if (!ok) throw new Exception("servo rejected");
    }
    static void Pose(MAVLinkInterface port, int position) {
        int[] roll = { 0, 1500, 1250, 1750, 1500, 1500, 2000 };
        int[] pitch = { 0, 1500, 1500, 1500, 1250, 1750, 1500 };
        if (position < 1 || position > 6) throw new Exception("invalid position " + position);
        Servo(port, 6, roll[position]);
        Servo(port, 7, pitch[position]);
        Servo(port, 8, 1500);
        Console.WriteLine("POSE=" + position);
        System.Threading.Thread.Sleep(4500);
        port.sendPacket(new MAVLink.mavlink_command_long_t { param1 = position, command = (ushort)MAVLink.MAV_CMD.ACCELCAL_VEHICLE_POS }, 1, 1);
        Console.WriteLine("CONFIRMED=" + position);
    }
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            var limit = DateTime.UtcNow.AddSeconds(8);
            bool disarmed = false;
            while (DateTime.UtcNow < limit) {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                if ((p.ToStructure<MAVLink.mavlink_heartbeat_t>().base_mode & 128) != 0) throw new Exception("armed");
                disarmed = true; break;
            }
            if (!disarmed) throw new Exception("no disarmed heartbeat");
            Console.WriteLine("INITIAL_ARMED=False");
            Servo(port, 6, 1500); Servo(port, 7, 1500); Servo(port, 8, 1500); Servo(port, 5, 1150);
            System.Threading.Thread.Sleep(4000);
            bool ok = port.doCommand(1, 1, MAVLink.MAV_CMD.PREFLIGHT_CALIBRATION, 0, 0, 0, 0, 1, 0, 0, true);
            Console.WriteLine("START_RETURN=" + ok);
            if (!ok) throw new Exception("start rejected");
            int last = 0;
            limit = DateTime.UtcNow.AddSeconds(100);
            while (DateTime.UtcNow < limit) {
                var p = port.readPacket();
                if (p.sysid != 1 || p.compid != 1) continue;
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT) {
                    if ((p.ToStructure<MAVLink.mavlink_heartbeat_t>().base_mode & 128) != 0) throw new Exception("armed during calibration");
                } else if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.COMMAND_LONG) {
                    var cmd = p.ToStructure<MAVLink.mavlink_command_long_t>();
                    if (cmd.command != (ushort)MAVLink.MAV_CMD.ACCELCAL_VEHICLE_POS) continue;
                    int pos = (int)cmd.param1;
                    Console.WriteLine("REQUEST=" + pos);
                    if (pos >= 1 && pos <= 6 && pos != last) { if (pos != last + 1) throw new Exception("unexpected sequence"); Pose(port, pos); last = pos; }
                    else if (pos == 16777215) { Console.WriteLine("RESULT=SUCCESS_POSITION"); return 0; }
                    else if (pos == 16777216) throw new Exception("failed position result");
                } else if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.STATUSTEXT) {
                    string status = Encoding.ASCII.GetString(p.ToStructure<MAVLink.mavlink_statustext_t>().text).TrimEnd('\0');
                    Console.WriteLine("STATUS=" + status);
                    if (status.ToLowerInvariant().Contains("calibration successful")) { Console.WriteLine("RESULT=SUCCESS_TEXT"); return 0; }
                    if (status.ToLowerInvariant().Contains("calibration failed")) throw new Exception("calibration failed text");
                }
            }
            throw new Exception("deadline at position " + last);
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
