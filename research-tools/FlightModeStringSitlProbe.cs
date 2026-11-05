// Original ArduPilot assembly with test-patched Utilities data-directory routing.
using System;
using System.IO;
using System.Security.Cryptography;
using MissionPlanner;
using MissionPlanner.ArduPilot;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class FlightModeStringSitlProbe
{
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            string dataDir = Path.GetFullPath(Settings.GetDataDirectory()).TrimEnd(Path.DirectorySeparatorChar);
            string expected = Path.GetFullPath(args[1]).TrimEnd(Path.DirectorySeparatorChar);
            if (!String.Equals(dataDir, expected, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("unexpected data directory " + dataDir);
            string metadata = Path.Combine(dataDir, "ArduCopter.apm.pdef.xml");
            using (var stream = File.OpenRead(metadata)) using (var hash = SHA256.Create())
                Console.WriteLine("COPTER_METADATA_SHA256=" + BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant());
            Console.WriteLine("DATA_DIR=" + dataDir);
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            var beforeDeadline = DateTime.UtcNow.AddSeconds(8);
            bool before = false;
            while (DateTime.UtcNow < beforeDeadline)
            {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                if (hb.custom_mode != 0 || (hb.base_mode & 128) != 0) throw new InvalidOperationException("unexpected initial heartbeat");
                before = true; break;
            }
            if (!before) throw new TimeoutException("initial heartbeat");
            Console.WriteLine("INITIAL_MODE=0 ARMED=False FIRMWARE=" + port.MAVlist[1, 1].cs.firmware);
            if (port.MAVlist[1, 1].cs.firmware != Firmwares.ArduCopter2) throw new InvalidOperationException("wrong firmware");
            var translated = new MAVLink.mavlink_set_mode_t();
            bool found = port.translateMode(1, 1, "gUiDeD", ref translated);
            Console.WriteLine("TRANSLATED=" + found + " TARGET=" + translated.target_system + " BASE=" + translated.base_mode + " CUSTOM=" + translated.custom_mode);
            if (!found || translated.custom_mode != 4 || translated.base_mode != 1) throw new InvalidOperationException("unexpected translation");
            var field = typeof(ParameterMetaDataRepositoryAPMpdef).GetField("_parameterMetaDataXML", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
            var docs = (System.Collections.IDictionary)field.GetValue(null);
            bool loaded = docs.Contains("ArduCopter");
            bool matches = loaded && System.Xml.Linq.XNode.DeepEquals((System.Xml.Linq.XDocument)docs["ArduCopter"], System.Xml.Linq.XDocument.Load(metadata));
            string pdefValues = ParameterMetaDataRepositoryAPMpdef.GetParameterMetaData("FLTMODE1", "Values", "ArduCopter2");
            string chosenValues = ParameterMetaDataRepository.GetParameterMetaData("FLTMODE1", "Values", "ArduCopter2");
            Console.WriteLine("PDEF_LOADED=" + loaded + " XML_MATCH=" + matches + " VALUES_NONEMPTY=" + (pdefValues != "") + " VALUES_MATCH=" + (pdefValues == chosenValues));
            if (!loaded || !matches || pdefValues == "" || pdefValues != chosenValues) throw new InvalidOperationException("metadata source mismatch");
            port.setMode(1, 1, "not-a-mode");
            Console.WriteLine("INVALID_STRING_RETURNED");
            System.Threading.Thread.Sleep(300);
            port.setMode(1, 1, "gUiDeD");
            Console.WriteLine("VALID_STRING_RETURNED");
            var deadline = DateTime.UtcNow.AddSeconds(8);
            while (DateTime.UtcNow < deadline)
            {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                if ((hb.base_mode & 128) != 0) throw new InvalidOperationException("armed heartbeat");
                if (hb.custom_mode == 4) { Console.WriteLine("FINAL_MODE=4 ARMED=False"); return 0; }
            }
            throw new TimeoutException("GUIDED heartbeat");
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
