// Synthetic all-void HGT data; disposable SITL only.
using System;
using System.IO;
using System.Security.Cryptography;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class TerrainInvalidSitlProbe
{
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            string directory = Path.GetFullPath(args[1]);
            using (var input = File.OpenRead(Path.Combine(directory, "S36E149.hgt"))) using (var hash = SHA256.Create())
                Console.WriteLine("FIXTURE_SHA256=" + BitConverter.ToString(hash.ComputeHash(input)).Replace("-", "").ToLowerInvariant());
            srtm.datadirectory = directory;
            var sample = srtm.getAltitude(-35.363261, 149.165230);
            Console.WriteLine("SRTM_TYPE=" + sample.currenttype);
            if (sample.currenttype != srtm.tiletype.invalid) throw new Exception("expected void sample");
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            port.requestDatastream(MAVLink.MAV_DATA_STREAM.ALL, 4, 1, 1);
            Console.WriteLine("REQUESTED_ALL_STREAMS_HZ=4");
            var deadline = DateTime.UtcNow.AddSeconds(20);
            var nextCheck = DateTime.MinValue;
            int requests = 0, pendingReports = 0;
            while (DateTime.UtcNow < deadline) {
                if (DateTime.UtcNow >= nextCheck) { port.Terrain.checkTerrain(-35.363261, 149.165230); nextCheck = DateTime.UtcNow.AddSeconds(4); }
                var p = port.readPacket();
                if (p.sysid != 1 || p.compid != 1) continue;
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT && (p.ToStructure<MAVLink.mavlink_heartbeat_t>().base_mode & 128) != 0) throw new Exception("armed");
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.TERRAIN_REQUEST) requests++;
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.TERRAIN_REPORT) {
                    var report = p.ToStructure<MAVLink.mavlink_terrain_report_t>();
                    if (report.pending > 0 && report.loaded == 0) pendingReports++;
                }
            }
            Console.WriteLine("REQUEST_COUNT=" + requests + " PENDING_REPORT_COUNT=" + pendingReports);
            if (requests < 2 || pendingReports == 0) throw new Exception("insufficient request evidence");
            return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
