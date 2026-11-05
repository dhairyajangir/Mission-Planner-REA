// Synthetic constant-height local tile; disposable SITL only.
using System;
using System.IO;
using System.Security.Cryptography;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class TerrainFixtureSitlProbe
{
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            string directory = Path.GetFullPath(args[1]);
            string tile = Path.Combine(directory, "S36E149.hgt");
            using (var input = File.OpenRead(tile)) using (var hash = SHA256.Create())
                Console.WriteLine("FIXTURE_SHA256=" + BitConverter.ToString(hash.ComputeHash(input)).Replace("-", "").ToLowerInvariant());
            srtm.datadirectory = directory;
            var sample = srtm.getAltitude(-35.363261, 149.165230);
            Console.WriteLine("SRTM_TYPE=" + sample.currenttype + " HEIGHT=" + sample.alt + " SOURCE=" + sample.altsource);
            if (sample.currenttype != srtm.tiletype.valid || Math.Abs(sample.alt - 321) > 0.001) throw new Exception("fixture read failed");
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            var deadline = DateTime.UtcNow.AddSeconds(65);
            var nextCheck = DateTime.MinValue;
            int requests = 0;
            while (DateTime.UtcNow < deadline) {
                if (DateTime.UtcNow >= nextCheck) {
                    port.Terrain.checkTerrain(-35.363261, 149.165230);
                    Console.WriteLine("SENT_TERRAIN_CHECK");
                    nextCheck = DateTime.UtcNow.AddSeconds(4);
                }
                var p = port.readPacket();
                if (p.sysid != 1 || p.compid != 1) continue;
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT) {
                    if ((p.ToStructure<MAVLink.mavlink_heartbeat_t>().base_mode & 128) != 0) throw new Exception("armed");
                } else if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.TERRAIN_REQUEST) {
                    var req = p.ToStructure<MAVLink.mavlink_terrain_request_t>();
                    Console.WriteLine("REQUEST_LAT=" + req.lat + " LON=" + req.lon + " SPACING=" + req.grid_spacing + " MASK=" + req.mask);
                    requests++;
                } else if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.TERRAIN_REPORT) {
                    var report = p.ToStructure<MAVLink.mavlink_terrain_report_t>();
                    Console.WriteLine("REPORT_LAT=" + report.lat + " LON=" + report.lon + " HEIGHT=" + report.terrain_height + " PENDING=" + report.pending + " LOADED=" + report.loaded);
                    if (report.lat == -353632610 && report.lon == 1491652300 && Math.Abs(report.terrain_height - 321) < 0.01 && requests > 0) {
                        Console.WriteLine("FIXTURE_REPORT_MATCH=True"); return 0;
                    }
                }
            }
            throw new Exception("terrain report timeout; requests=" + requests);
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
