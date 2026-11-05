// Original command methods; one synthetic IN_PROGRESS ACK and no terminal ACK.
using System;
using System.Diagnostics;
using System.IO;
using MissionPlanner;
public static class CommandProgressOnlyProbe
{
    public static int Main(string[] args)
    {
        try
        {
            byte[] fixture = File.ReadAllBytes(args[0]);
            foreach (string form in new[] { "long", "int" })
            {
                var serial = new MemorySerial(fixture);
                var port = new MAVLinkInterface { BaseStream = serial };
                port.sysidcurrent = 1; port.compidcurrent = 1;
                var watch = Stopwatch.StartNew();
                string outcome;
                try
                {
                    bool result = form == "long"
                        ? port.doCommand(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true)
                        : port.doCommandInt(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true);
                    outcome = "RESULT=" + result;
                }
                catch (TimeoutException ex) { outcome = "TIMEOUT=" + ex.Message; }
                watch.Stop();
                Console.WriteLine("FORM=" + form + " " + outcome + " REMAINING=" + serial.BytesToRead +
                                  " GIVE=" + port.giveComport + " ELAPSED_MS=" + watch.ElapsedMilliseconds);
                if ((form == "long" && outcome != "TIMEOUT=Timeout on read - doCommand") ||
                    (form == "int" && outcome != "RESULT=False") || serial.BytesToRead != 0 || port.giveComport)
                    throw new InvalidOperationException("unexpected progress-only result " + form);
                serial.Dispose();
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
