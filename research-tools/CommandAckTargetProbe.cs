// Original command methods; synthetic MAVLink 2 ACK target fields, no vehicle.
using System;
using System.IO;
using MissionPlanner;
public static class CommandAckTargetProbe
{
    public static int Main(string[] args)
    {
        try
        {
            foreach (string form in new[] { "long", "int" })
            foreach (string name in new[] { "wrong-target-then-denied", "matching-denied", "broadcast-accepted" })
            {
                var serial = new MemorySerial(File.ReadAllBytes(Path.Combine(args[0], name + ".bin")));
                var port = new MAVLinkInterface { BaseStream = serial };
                port.sysidcurrent = 1; port.compidcurrent = 1;
                bool result = form == "long"
                    ? port.doCommand(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true)
                    : port.doCommandInt(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true);
                Console.WriteLine("FORM=" + form + " CASE=" + name + " RESULT=" + result + " REMAINING=" + serial.BytesToRead + " GIVE=" + port.giveComport);
                bool expected = name != "matching-denied";
                int remaining = name == "wrong-target-then-denied" ? 22 : 0;
                if (result != expected || serial.BytesToRead != remaining || port.giveComport)
                    throw new InvalidOperationException("unexpected target case " + form + " " + name);
                serial.Dispose();
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
