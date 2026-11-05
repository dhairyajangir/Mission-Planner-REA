using System;
using System.IO;
using System.Security.Cryptography;
using MissionPlanner;
using MissionPlanner.ArduPilot;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class InvalidFlightModeStringSitlProbe
{
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            string dir = Path.GetFullPath(Settings.GetDataDirectory()).TrimEnd(Path.DirectorySeparatorChar);
            if (!String.Equals(dir, Path.GetFullPath(args[1]).TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase)) throw new Exception("wrong data directory");
            string metadata = Path.Combine(dir, "ArduCopter.apm.pdef.xml");
            using (var f = File.OpenRead(metadata)) using (var hash = SHA256.Create()) Console.WriteLine("COPTER_METADATA_SHA256=" + BitConverter.ToString(hash.ComputeHash(f)).Replace("-", "").ToLowerInvariant());
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            var beforeDeadline = DateTime.UtcNow.AddSeconds(8);
            bool before = false;
            while (DateTime.UtcNow < beforeDeadline) {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                if (hb.custom_mode != 0 || (hb.base_mode & 128) != 0) throw new Exception("unexpected initial heartbeat");
                before = true; break;
            }
            if (!before || port.MAVlist[1,1].cs.firmware != Firmwares.ArduCopter2) throw new Exception("initial state");
            Console.WriteLine("INITIAL_MODE=0 ARMED=False FIRMWARE=ArduCopter2");
            port.setMode(1, 1, "not-a-mode");
            Console.WriteLine("INVALID_STRING_RETURNED");
            var field = typeof(ParameterMetaDataRepositoryAPMpdef).GetField("_parameterMetaDataXML", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
            var docs = (System.Collections.IDictionary)field.GetValue(null);
            bool loaded = docs.Contains("ArduCopter");
            bool matches = loaded && System.Xml.Linq.XNode.DeepEquals((System.Xml.Linq.XDocument)docs["ArduCopter"], System.Xml.Linq.XDocument.Load(metadata));
            string pdef = ParameterMetaDataRepositoryAPMpdef.GetParameterMetaData("FLTMODE1", "Values", "ArduCopter2");
            string selected = ParameterMetaDataRepository.GetParameterMetaData("FLTMODE1", "Values", "ArduCopter2");
            Console.WriteLine("PDEF_LOADED=" + loaded + " XML_MATCH=" + matches + " VALUES_NONEMPTY=" + (pdef != "") + " VALUES_MATCH=" + (pdef == selected));
            if (!loaded || !matches || pdef == "" || pdef != selected) throw new Exception("metadata mismatch");
            var deadline = DateTime.UtcNow.AddSeconds(7);
            int count = 0;
            while (DateTime.UtcNow < deadline) {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                if (hb.custom_mode != 0 || (hb.base_mode & 128) != 0) throw new Exception("unexpected final heartbeat");
                count++;
            }
            if (count == 0) throw new Exception("no heartbeats");
            Console.WriteLine("FINAL_MODE=0 ARMED=False HEARTBEATS=" + count);
            return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
