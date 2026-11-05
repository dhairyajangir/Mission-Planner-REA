// Tests armed calibration rejection only against a disposable local simulator.
using System;
using MissionPlanner;
using MissionPlanner.Comms;
public static class AccelCalibrationArmedProbe
{
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            System.Threading.Thread.Sleep(6000);
            bool armed = port.doCommand(1, 1, MAVLink.MAV_CMD.COMPONENT_ARM_DISARM, 1, 21196, 0, 0, 0, 0, 0, true);
            Console.WriteLine("ARM_COMMAND_RETURN=" + armed);
            if (!armed) throw new Exception("simulated arm rejected");
            bool heartbeatArmed = false;
            var deadline = DateTime.UtcNow.AddSeconds(8);
            while (DateTime.UtcNow < deadline) {
                var p = port.readPacket();
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT && p.sysid == 1 && p.compid == 1 && (p.ToStructure<MAVLink.mavlink_heartbeat_t>().base_mode & 128) != 0) { heartbeatArmed = true; break; }
            }
            if (!heartbeatArmed) throw new Exception("armed heartbeat not observed");
            Console.WriteLine("ARMED_HEARTBEAT=True");
            bool accepted = port.doCommand(1, 1, MAVLink.MAV_CMD.PREFLIGHT_CALIBRATION, 0, 0, 0, 0, 1, 0, 0, true);
            Console.WriteLine("PREFLIGHT_CALIBRATION_RETURN=" + accepted);
            if (!accepted) throw new Exception("unexpected immediate return");
            bool failedAck = false;
            deadline = DateTime.UtcNow.AddSeconds(6);
            while (DateTime.UtcNow < deadline) {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.COMMAND_ACK || p.sysid != 1 || p.compid != 1) continue;
                var ack = p.ToStructure<MAVLink.mavlink_command_ack_t>();
                if (ack.command == (ushort)MAVLink.MAV_CMD.PREFLIGHT_CALIBRATION) {
                    Console.WriteLine("PREFLIGHT_ACK_RESULT=" + ack.result);
                    failedAck = ack.result == (byte)MAVLink.MAV_RESULT.FAILED;
                    break;
                }
            }
            if (!failedAck) throw new Exception("failed calibration ACK not observed");
            bool disarm = port.doCommand(1, 1, MAVLink.MAV_CMD.COMPONENT_ARM_DISARM, 0, 21196, 0, 0, 0, 0, 0, true);
            Console.WriteLine("DISARM_COMMAND_RETURN=" + disarm);
            if (!disarm) throw new Exception("simulated disarm rejected");
            deadline = DateTime.UtcNow.AddSeconds(8);
            while (DateTime.UtcNow < deadline) {
                var p = port.readPacket();
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT && p.sysid == 1 && p.compid == 1 && (p.ToStructure<MAVLink.mavlink_heartbeat_t>().base_mode & 128) == 0) { Console.WriteLine("FINAL_ARMED=False"); return 0; }
            }
            throw new Exception("disarmed heartbeat not observed");
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
