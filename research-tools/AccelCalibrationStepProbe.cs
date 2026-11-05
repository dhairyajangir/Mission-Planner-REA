// Disarmed SITL: send wrong then correct response to the first calibration prompt.
using System;
using MissionPlanner;
using MissionPlanner.Comms;
public static class AccelCalibrationStepProbe
{
    static void SendPosition(MAVLinkInterface port, float position) {
        port.sendPacket(new MAVLink.mavlink_command_long_t { param1 = position, command = (ushort)MAVLink.MAV_CMD.ACCELCAL_VEHICLE_POS }, 1, 1);
        Console.WriteLine("SENT_POSITION=" + position);
    }
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            var initialEnd = DateTime.UtcNow.AddSeconds(8);
            bool disarmed = false;
            while (DateTime.UtcNow < initialEnd) {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                if ((hb.base_mode & 128) != 0) throw new Exception("armed");
                disarmed = true; break;
            }
            if (!disarmed) throw new Exception("no disarmed heartbeat");
            Console.WriteLine("INITIAL_ARMED=False");
            bool ok = port.doCommand(1, 1, MAVLink.MAV_CMD.PREFLIGHT_CALIBRATION, 0, 0, 0, 0, 1, 0, 0, true);
            Console.WriteLine("START_RETURN=" + ok);
            if (!ok) throw new Exception("calibration start rejected");
            int phase = 0, repeated = 0;
            var end = DateTime.UtcNow.AddSeconds(25);
            while (DateTime.UtcNow < end) {
                var p = port.readPacket();
                if (p.sysid != 1 || p.compid != 1) continue;
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT) {
                    var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                    if ((hb.base_mode & 128) != 0) throw new Exception("armed");
                }
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.COMMAND_LONG) continue;
                var cmd = p.ToStructure<MAVLink.mavlink_command_long_t>();
                if (cmd.command != (ushort)MAVLink.MAV_CMD.ACCELCAL_VEHICLE_POS) continue;
                Console.WriteLine("POSITION_REQUEST=" + cmd.param1 + " PHASE=" + phase);
                if (phase == 0 && cmd.param1 == 1) { SendPosition(port, 2); phase = 1; }
                else if (phase == 1 && cmd.param1 == 1) {
                    repeated++;
                    if (repeated == 3) { SendPosition(port, 1); phase = 2; }
                }
                else if (phase == 2 && cmd.param1 == 2) { Console.WriteLine("NEXT_POSITION=2"); return 0; }
            }
            throw new Exception("next position not observed, phase=" + phase);
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
