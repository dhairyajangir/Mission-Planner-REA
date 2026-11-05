// Test the distributed parser with synthetic heartbeats. No Open(), socket or serial device.
using System;
using System.IO;
using System.Linq;
using System.Globalization;
using MissionPlanner;

public static class MultiVehicleParserProbe
{
    static void Run(string folder, string name, int count)
    {
        Console.WriteLine("CASE=" + name);
        var port = new MAVLinkInterface();
        var serial = new MemorySerial(File.ReadAllBytes(Path.Combine(folder, name)));
        port.BaseStream = serial;
        for (int i = 0; i < count; i++)
        {
            var message = port.readPacket();
            Console.WriteLine("READ=" + i + " LENGTH=" + (message.buffer == null ? 0 : message.buffer.Length) +
                " SYS=" + message.sysid + " COMP=" + message.compid + " VISIBLE=" + port.MAVlist.Count +
                " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent + " REMAINING=" + serial.BytesToRead);
        }
        var visible = port.MAVlist.Select(x => x.sysid + ":" + x.compid + ":" + x.aptype).OrderBy(x => x).ToArray();
        Console.WriteLine("VISIBLE_LIST=" + String.Join(",", visible));
        Console.WriteLine("BAD_SYSTEM_VISIBLE=" + port.MAVlist.Contains(3, 1, false));
        serial.Dispose();
    }
    static void ParamIsolation(string folder)
    {
        Console.WriteLine("CASE=param-isolation.bin");
        var port = new MAVLinkInterface();
        var serial = new MemorySerial(File.ReadAllBytes(Path.Combine(folder, "param-isolation.bin")));
        port.BaseStream = serial;
        for (int i = 0; i < 7; i++)
        {
            var message = port.readPacket();
            Console.WriteLine("READ=" + i + " LENGTH=" + (message.buffer == null ? 0 : message.buffer.Length) +
                " SYS=" + message.sysid + " COMP=" + message.compid + " MSG=" + message.msgid +
                " REMAINING=" + serial.BytesToRead);
        }
        foreach (var id in new[] { new[] {1, 1}, new[] {2, 1}, new[] {1, 100} })
        {
            var param = port.MAVlist[id[0], id[1]].param["TEST_VAL"];
            Console.WriteLine("PARAM=" + id[0] + ":" + id[1] + " VALUE=" +
                (param == null ? "<missing>" : param.Value.ToString("R", CultureInfo.InvariantCulture)));
        }
        Console.WriteLine("SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent + " VISIBLE=" + port.MAVlist.Count);
        serial.Dispose();
    }
    public static int Main(string[] args)
    {
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            Run(args[0], "vehicle-first.bin", 5);
            Run(args[0], "gcs-first.bin", 3);
            Run(args[0], "bad-only.bin", 1);
            ParamIsolation(args[0]);
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
