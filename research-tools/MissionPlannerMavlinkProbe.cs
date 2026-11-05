// Invokes the original Mission Planner managed communication libraries against
// an isolated SITL TCP listener. Does not invoke the GUI or issue flight commands.
using System;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;

public static class MissionPlannerMavlinkProbe
{
    public static int Main(string[] args)
    {
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            var port = new MAVLinkInterface();
            port.BaseStream = new TcpSerial { Host = args.Length > 0 ? args[0] : "127.0.0.1", Port = Environment.GetEnvironmentVariable("MP_PROBE_PORT") ?? "6160" };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen);
            Console.WriteLine("SYSTEM=" + port.sysidcurrent + " COMPONENT=" + port.compidcurrent);
            if (!port.BaseStream.IsOpen) return 2;
            Console.WriteLine("MISSION_COUNT=" + port.getWPCount());
            if (Array.IndexOf(args, "--param-list") >= 0 || Array.IndexOf(args, "--param-list-ftp") >= 0)
            {
                System.Threading.Thread.Sleep(15000);
                var reader = new System.Threading.Thread(() =>
                {
                    while (port.BaseStream.IsOpen)
                    {
                        try { port.readPacket(); }
                        catch (Exception ex) { Console.WriteLine("PACKET_READER_ERROR=" + ex.Message); break; }
                    }
                });
                reader.IsBackground = true;
                reader.Start();
                var parameters = Array.IndexOf(args, "--param-list-ftp") >= 0
                    ? port.getParamListMavftp((byte)port.sysidcurrent, (byte)port.compidcurrent)
                    : port.getParamList((byte)port.sysidcurrent, (byte)port.compidcurrent);
                Console.WriteLine("PARAM_LIST_RECEIVED=" + parameters.TotalReceived);
                Console.WriteLine("PARAM_LIST_REPORTED=" + parameters.TotalReported);
                if (parameters.TotalReported <= 0 || parameters.TotalReceived != parameters.TotalReported) return 5;
            }
            if (Array.IndexOf(args, "--logs") >= 0)
            {
                System.Threading.Thread.Sleep(15000);
                var logs = port.GetLogList();
                Console.WriteLine("LOG_LIST_COUNT=" + logs.Count);
                foreach (var item in logs)
                    Console.WriteLine("LOG_ENTRY=" + item.id + "," + item.size);
            }
            if (Array.IndexOf(args, "--download-log") >= 0)
            {
                System.Threading.Thread.Sleep(15000);
                var logs = port.GetLogList();
                Console.WriteLine("LOG_LIST_COUNT=" + logs.Count);
                if (logs.Count == 0) throw new InvalidOperationException("No simulator log available");
                var entry = logs[0];
                Console.WriteLine("LOG_ENTRY=" + entry.id + "," + entry.size);
                // The first log belongs to an earlier, stopped simulator process.
                // GetLog consumes packet events; the GUI normally runs a separate reader.
                var reader = new System.Threading.Thread(() =>
                {
                    while (port.BaseStream.IsOpen)
                    {
                        try { port.readPacket(); }
                        catch (Exception ex) { Console.WriteLine("PACKET_READER_ERROR=" + ex.Message); break; }
                    }
                });
                reader.IsBackground = true;
                reader.Start();
                var path = port.GetLog((byte)port.sysidcurrent, (byte)port.compidcurrent, entry.id).GetAwaiter().GetResult();
                var destination = Environment.GetEnvironmentVariable("MP_PROBE_LOG_DEST");
                if (String.IsNullOrEmpty(destination)) throw new InvalidOperationException("MP_PROBE_LOG_DEST is required");
                System.IO.File.Copy(path, destination, false);
                Console.WriteLine("LOG_DOWNLOAD_PATH=" + destination);
                Console.WriteLine("LOG_DOWNLOAD_BYTES=" + new System.IO.FileInfo(destination).Length);
            }
            if (Array.IndexOf(args, "--mission-types") >= 0)
            {
                System.Threading.Thread.Sleep(15000);
                foreach (var type in new[] { MAVLink.MAV_MISSION_TYPE.MISSION,
                                             MAVLink.MAV_MISSION_TYPE.FENCE,
                                             MAVLink.MAV_MISSION_TYPE.RALLY })
                {
                    var count = port.getWPCount((byte)port.sysidcurrent, (byte)port.compidcurrent, type);
                    Console.WriteLine("TYPE_COUNT=" + type + ":" + count);
                }
            }
            if (Array.IndexOf(args, "--params") >= 0)
            {
                System.Threading.Thread.Sleep(15000);
                // LOG_DISARMED is present in this specific 4.7.2 SITL build.
                // This instance is a disposable simulator; its value is restored.
                const string paramName = "LOG_DISARMED";
                var before = port.GetParam(paramName);
                var desired = before == 0 ? 1.0 : 0.0;
                var changed = false;
                try
                {
                    changed = port.setParam(paramName, desired);
                    var readback = port.GetParam(paramName);
                    var missing = port.setParam("THIS_PARAM_DOES_NOT_EXIST", 123);
                    Console.WriteLine("PARAM_BEFORE=" + before);
                    Console.WriteLine("PARAM_SET_OK=" + changed);
                    Console.WriteLine("PARAM_READBACK=" + readback);
                    Console.WriteLine("MISSING_PARAM_ACCEPTED=" + missing);
                    if (!changed || Math.Abs(readback - desired) > 0.01 || missing) return 4;
                }
                finally
                {
                    if (changed)
                    {
                        var restored = port.setParam(paramName, before);
                        var after = port.GetParam(paramName);
                        Console.WriteLine("PARAM_RESTORE_OK=" + restored);
                        Console.WriteLine("PARAM_AFTER=" + after);
                        if (!restored || Math.Abs(after - before) > 0.01)
                            throw new InvalidOperationException("Simulator parameter restoration failed");
                    }
                }
            }
            if (Array.IndexOf(args, "--roundtrip") >= 0)
            {
                System.Threading.Thread.Sleep(15000);
                var home = new Locationwp().Set(-35.363261, 149.165230, 0, (ushort)MAVLink.MAV_CMD.WAYPOINT);
                var wp = new Locationwp().Set(-35.363, 149.1655, 20, (ushort)MAVLink.MAV_CMD.WAYPOINT);
                port.setWPTotal(2);
                var r0 = port.setWP(home, 0, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT, use_int: true);
                var r1 = port.setWP(wp, 1, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT, use_int: true);
                var count = port.getWPCount();
                var returned = port.getWP(1);
                Console.WriteLine("UPLOAD_RESULTS=" + r0 + "," + r1);
                Console.WriteLine("ROUNDTRIP_COUNT=" + count);
                Console.WriteLine("RETURNED=" + returned.lat.ToString("R", System.Globalization.CultureInfo.InvariantCulture) + "," + returned.lng.ToString("R", System.Globalization.CultureInfo.InvariantCulture) + "," + returned.alt);
                if (r0 != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED || r1 != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED || count != 2 || Math.Abs(returned.lat - wp.lat) > 0.0000001 || Math.Abs(returned.lng - wp.lng) > 0.0000001 || Math.Abs(returned.alt - wp.alt) > 0.01) return 3;
            }
            port.Close();
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            return 1;
        }
    }
}
