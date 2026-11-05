// Original MAVLinkInterface with in-memory synthetic ACKs; no socket or vehicle.
using System;
using System.IO;
using MissionPlanner;

public static class CommandAckSyntheticProbe
{
    public static int Main(string[] args)
    {
        try
        {
            foreach (string name in new[] { "wrong-system", "wrong-component", "wrong-command", "in-progress", "denied", "no-ack" })
            {
                var serial = new MemorySerial(File.ReadAllBytes(Path.Combine(args[0], name + ".bin")));
                var port = new MAVLinkInterface { BaseStream = serial };
                port.sysidcurrent = 1; port.compidcurrent = 1;
                bool result = port.doCommand(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, name != "no-ack");
                Console.WriteLine("CASE=" + name + " RESULT=" + result + " REMAINING=" + serial.BytesToRead + " GIVE=" + port.giveComport);
                bool expected = name == "in-progress" || name == "no-ack";
                int expectedRemaining = name == "no-ack" ? 11 : 0;
                if (result != expected || serial.BytesToRead != expectedRemaining || port.giveComport)
                    throw new InvalidOperationException("unexpected result " + name);
                serial.Dispose();
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
