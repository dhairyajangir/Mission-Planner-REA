// Use the original Mission Planner communication library against a disposable localhost SITL.
using System;
using System.IO;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;

public static class MissionPlannerNonfiniteProbe
{
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            var path = args[0];
            File.WriteAllText(path, "LOG_DISARMED,NaN\n");
            var parsed = ParamFile.loadParamFile(path)["LOG_DISARMED"];
            Console.WriteLine("PARSED_NAN=" + Double.IsNaN(parsed));
            Console.WriteLine("PARAM_ERROR_ENUM_PRESENT=" + Enum.IsDefined(typeof(MAVLink.MAVLINK_MSG_ID), "PARAM_ERROR"));
            port = new MAVLinkInterface();
            port.BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[1] };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen);
            if (!port.BaseStream.IsOpen) throw new InvalidOperationException("simulator connection not open");
            Thread.Sleep(15000);
            double before = port.GetParam("LOG_DISARMED");
            Console.WriteLine("BEFORE=" + before);
            if (before != 0) throw new InvalidOperationException("unexpected simulator baseline");
            try
            {
                bool accepted = port.setParam("LOG_DISARMED", parsed);
                Console.WriteLine("NONFINITE_RETURN=" + accepted);
            }
            catch (Exception ex) { Console.WriteLine("NONFINITE_EXCEPTION=" + ex.GetType().FullName + " MESSAGE=" + ex.Message); }
            Console.WriteLine("AFTER_NONFINITE=" + port.GetParam("LOG_DISARMED"));
            bool changed = false;
            try
            {
                changed = port.setParam("LOG_DISARMED", 1);
                Console.WriteLine("FINITE_SET=" + changed);
                Console.WriteLine("FINITE_READBACK=" + port.GetParam("LOG_DISARMED"));
            }
            finally
            {
                bool restored = port.setParam("LOG_DISARMED", before, true);
                Console.WriteLine("RESTORE_SET=" + restored);
                Console.WriteLine("RESTORE_READBACK=" + port.GetParam("LOG_DISARMED"));
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
