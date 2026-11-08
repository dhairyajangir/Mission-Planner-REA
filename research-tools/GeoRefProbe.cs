// Library-level probe of the original Mission Planner 1.3.83 photo geotagging core (GeoRefImageBase).
// Synthetic DataFlash text log + empty .jpg files whose "EXIF" times are seeded through the public filedatecache:
// no real photos, vehicle, link, simulator or network. Reports what the compiled library pairs and computes.
// Usage: GeoRefProbe.exe <dir with original MissionPlanner DLLs> <work dir> <output dir>
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using MissionPlanner.GeoRef;

public static class GeoRefProbe
{
    static readonly CultureInfo IC = CultureInfo.InvariantCulture;
    static string F(double v) { return v.ToString("R", IC); }
    const int Week = 2300;                 // GPS week used in the synthetic log
    const int Leap = 18;                   // true GPS-UTC offset since 2017-01-01
    static readonly DateTime GpsEpoch = new DateTime(1980, 1, 6, 0, 0, 0, DateTimeKind.Utc);

    // true UTC for a GPS week / millisecond-of-week
    static DateTime TrueUtc(int week, long ms) { return GpsEpoch.AddDays(week * 7).AddMilliseconds(ms).AddSeconds(-Leap); }

    public static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string p = Path.Combine(dir, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        return Run(Path.GetFullPath(args[1]), Path.GetFullPath(args[2]));
    }

    const long BaseMs = 345600000;         // ms into the week of the first GPS fix
    // GPS fixes every 200 ms for 20 s, 10 m/s east
    static string BuildLog(string path, IEnumerable<long> camOffsetsMs, int gpsLast = 100)
    {
        var sb = new StringBuilder();
        sb.AppendLine("FMT, 128, 89, FMT, BBnNZ, Type,Length,Name,Format,Columns");
        sb.AppendLine("FMT, 129, 49, GPS, QBIHBcLLefffB, TimeUS,Status,GMS,GWk,NSats,HDop,Lat,Lng,Alt,Spd,GCrs,VZ,U");
        sb.AppendLine("FMT, 130, 28, ATT, Qcccccc, TimeUS,DesRoll,Roll,DesPitch,Pitch,DesYaw,Yaw");
        sb.AppendLine("FMT, 131, 43, CAM, QIHLLeeeccC, TimeUS,GPSTime,GPSWeek,Lat,Lng,Alt,RelAlt,GPSAlt,Roll,Pitch,Yaw");
        double lat0 = -35.3632621, lng0 = 149.1652374;
        double mPerDegLng = 111320.0 * Math.Cos(lat0 * Math.PI / 180.0);
        Func<long, double> lngAt = off => lng0 + (off / 1000.0) * 10.0 / mPerDegLng;
        for (int k = 0; k <= gpsLast; k++)
        {
            long off = k * 200L;
            long timeUs = 10000000L + off * 1000;
            sb.AppendFormat(IC, "ATT, {0}, 0, 1.5, 0, -0.5, 0, 90\n", timeUs);
            sb.AppendFormat(IC, "GPS, {0}, 3, {1}, {2}, 12, 0.9, {3}, {4}, {5}, 10, 90, 0, 1\n", timeUs, BaseMs + off, Week,
                F(lat0), F(lngAt(off)), F(584.0 + k * 0.1));
        }
        foreach (long off in camOffsetsMs)
        {
            long timeUs = 10000000L + off * 1000;
            sb.AppendFormat(IC, "CAM, {0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}, 1.5, -0.5, 90\n", timeUs, BaseMs + off, Week,
                F(lat0), F(lngAt(off)), F(584.0), F(100.0), F(584.0));
        }
        File.WriteAllText(path, sb.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
        return path;
    }

    static string Photos(string root, string name, IList<DateTime> times, GeoRefImageBase g)
    {
        string d = Path.Combine(root, name);
        if (Directory.Exists(d)) Directory.Delete(d, true);
        Directory.CreateDirectory(d);
        for (int i = 0; i < times.Count; i++)
        {
            string f = Path.Combine(d, "IMG_" + (i + 1).ToString("0000") + ".jpg");
            File.WriteAllBytes(f, new byte[0]);
            g.filedatecache[f] = times[i];
        }
        return d;
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string work, string outDir)
    {
        try
        {
            Directory.CreateDirectory(work); Directory.CreateDirectory(outDir);
            var res = new StringBuilder("case,photo,photo_time_utc,matched,pic_time_utc,pic_lat,pic_lng,pic_alt_amsl,pic_rel_alt,delta_ms,expected_offset_ms,note\n");
            var msgs = new StringBuilder("case,message\n");
            Action<string, IEnumerable<string>> addMsgs = (c, m) => { foreach (var x in m) msgs.AppendFormat("{0},\"{1}\"\n", c, x.TrimEnd('\n').Replace("\"", "'")); };

            // ---- A: time conversion paths for the same instant -----------------------------------------------------
            string logA = BuildLog(Path.Combine(work, "a.log"), new long[] { 5000 });
            var ga = new GeoRefImageBase();
            var gpsLoc = ga.readGPSMsgInLog(logA);
            var camLoc = typeof(GeoRefImageBase).GetMethod("readCAMMsgInLog", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(ga, new object[] { logA }) as Dictionary<long, VehicleLocation>;
            DateTime truth5000 = TrueUtc(Week, BaseMs + 5000);
            var gpsAt = gpsLoc.Values.First(v => Math.Abs((v.Time - truth5000).TotalMilliseconds) < 100 || true && v.Lat != 0 && Math.Abs((v.Time.ToUniversalTime() - truth5000).TotalSeconds) < 30);
            var gpsFix = gpsLoc.Values.OrderBy(v => Math.Abs((v.Time.ToUniversalTime() - truth5000).TotalMilliseconds)).First();
            var cam = camLoc.Values.First();
            Console.WriteLine("GPS_FIXES={0} CAM_MSGS={1}", gpsLoc.Count, camLoc.Count);
            Console.WriteLine("TIME_TRUTH_UTC={0:o}", truth5000);
            Console.WriteLine("TIME_GPS_PATH_UTC={0:o} delta_ms={1}", gpsFix.Time.ToUniversalTime(), (gpsFix.Time.ToUniversalTime() - truth5000).TotalMilliseconds);
            Console.WriteLine("TIME_CAM_PATH_UTC={0:o} delta_ms={1}", cam.Time, (cam.Time - truth5000).TotalMilliseconds);
            Console.WriteLine("TIME_GETTIMEFROMGPS_17S={0:o}", ga.GetTimeFromGps(Week, (int)(BaseMs + 5000)));
            Console.WriteLine("GPS_KIND={0} CAM_KIND={1}", gpsFix.Time.Kind, cam.Time.Kind);

            // ---- B: GPS-offset mode, photos at shifts from the fix at 5.0 s -----------------------------------------
            long[] shifts = { 0, 50, 100, 130, 1200, 2400, 2600, -100, -2600 };
            Func<GeoRefImageBase, string, float, string, Dictionary<string, PictureInformation>> offsetRun = null;
            {
                var g = new GeoRefImageBase();
                var times = shifts.Select(s => truth5000.AddMilliseconds(s)).ToList();
                string d = Photos(work, "b", times, g);
                var log = new List<string>();
                var r = g.doworkGPSOFFSET(logA, d, 0f, "GPS", false, log.Add);
                addMsgs("B-offset0-utc-camera", log);
                for (int i = 0; i < shifts.Length; i++)
                {
                    string f = Path.Combine(d, "IMG_" + (i + 1).ToString("0000") + ".jpg");
                    PictureInformation p;
                    bool ok = r.TryGetValue(f, out p);
                    res.AppendFormat("B-offset0-utc-camera,{0},{1:o},{2},{3},{4},{5},{6},{7},{8},{9},{10}\n", Path.GetFileName(f), times[i], ok,
                        ok ? p.Time.ToUniversalTime().ToString("o") : "", ok ? F(p.Lat) : "", ok ? F(p.Lon) : "", ok ? F(p.AltAMSL) : "", ok ? F(p.RelAlt) : "",
                        ok ? F((p.Time.ToUniversalTime() - times[i]).TotalMilliseconds) : "", shifts[i], "shift " + shifts[i] + " ms from a fix");
                }
            }

            // ---- C: camera clock on local time (UTC+5:30) with and without the offset field --------------------------
            foreach (float offset in new[] { 0f, 19800f })
            {
                var g = new GeoRefImageBase();
                var times = new List<DateTime> { truth5000.AddHours(5.5).AddMilliseconds(0), truth5000.AddHours(5.5).AddMilliseconds(1000) };
                string d = Photos(work, "c" + (int)offset, times, g);
                var log = new List<string>();
                var r = g.doworkGPSOFFSET(logA, d, offset, "GPS", false, log.Add);
                string cname = "C-camera-utc+5.5-offset" + (int)offset;
                addMsgs(cname, log);
                for (int i = 0; i < times.Count; i++)
                {
                    string f = Path.Combine(d, "IMG_" + (i + 1).ToString("0000") + ".jpg");
                    PictureInformation p;
                    bool ok = r.TryGetValue(f, out p);
                    res.AppendFormat("{0},{1},{2:o},{3},{4},{5},{6},{7},{8},,,\n", cname, Path.GetFileName(f), times[i], ok,
                        ok ? p.Time.ToUniversalTime().ToString("o") : "", ok ? F(p.Lat) : "", ok ? F(p.Lon) : "", ok ? F(p.AltAMSL) : "", ok ? F(p.RelAlt) : "");
                }
            }

            // ---- D: CAM mode pairing: 8 CAM messages 1.5 s apart, photos at CAM times (UTC from the true 18 s offset) -
            long[] camOff = Enumerable.Range(0, 8).Select(i => 3000L + i * 1500).ToArray();
            string logD = BuildLog(Path.Combine(work, "d.log"), camOff);
            Func<string, string, long[], int[], int, int, string[]> camCase = (name, logPath, camOffs, photoIdx, dropstart, dropend) =>
            {
                var g = new GeoRefImageBase();
                var times = photoIdx.Select(i => TrueUtc(Week, BaseMs + camOffs[i]).AddMilliseconds(40)).ToList();
                string d = Photos(work, name, times, g);
                var log = new List<string>();
                var r = g.doworkCAM(logPath, d, "GPS", log.Add, dropstart, dropend);
                addMsgs(name, log);
                var rows = new List<string>();
                for (int i = 0; i < times.Count; i++)
                {
                    string f = Path.Combine(d, "IMG_" + (i + 1).ToString("0000") + ".jpg");
                    PictureInformation p;
                    bool ok = r != null && r.TryGetValue(f, out p) && true;
                    p = null; if (r != null) r.TryGetValue(f, out p);
                    ok = p != null;
                    // which CAM message index (0..7) did it get? derive from longitude vs the 8 CAM offsets
                    int matchedCam = -1;
                    if (ok)
                        for (int k = 0; k < camOffs.Length; k++)
                        {
                            double lng = 149.1652374 + (camOffs[k] / 1000.0) * 10.0 / (111320.0 * Math.Cos(-35.3632621 * Math.PI / 180.0));
                            if (Math.Abs(p.Lon - lng) < 1e-9) matchedCam = k;
                        }
                    res.AppendFormat("{0},{1},{2:o},{3},{4},{5},{6},{7},{8},{9},,photo expects CAM {10}; paired with CAM {11}\n", name, Path.GetFileName(f), times[i], ok,
                        ok ? p.Time.ToString("o") : "", ok ? F(p.Lat) : "", ok ? F(p.Lon) : "", ok ? F(p.AltAMSL) : "", ok ? F(p.RelAlt) : "",
                        ok ? F((p.Time - times[i]).TotalMilliseconds) : "", photoIdx[i], matchedCam);
                }
                return null;
            };
            camCase("D1-cam-all-photos", logD, camOff, new[] { 0, 1, 2, 3, 4, 5, 6, 7 }, 0, 0);
            camCase("D2-cam-photo-3-missing", logD, camOff, new[] { 0, 1, 2, 4, 5, 6, 7 }, 0, 0);
            camCase("D3-cam-drop-start1-end1", logD, camOff, new[] { 1, 2, 3, 4, 5, 6 }, 1, 1);

            // E: CAM messages closer than the minimum shutter interval (0.5 s); photos at all four CAM times
            long[] closeOff = { 3000, 3300, 6000, 9000 };
            string logE = BuildLog(Path.Combine(work, "e.log"), closeOff);
            camCase("E-cam-close-pair", logE, closeOff, new[] { 0, 1, 2, 3 }, 0, 0);

            // F: GPS-offset search radius. GPS fixes only for the first 5 s; photos 2.4 s, 2.6 s and 4.9 s after the last fix.
            string logF = BuildLog(Path.Combine(work, "f.log"), new long[0], 25);
            {
                var g = new GeoRefImageBase();
                DateTime lastFix = TrueUtc(Week, BaseMs + 25 * 200);
                long[] gaps = { 2400, 2499, 2500, 2600, 4900 };
                var times = gaps.Select(s => lastFix.AddMilliseconds(s)).ToList();
                string d = Photos(work, "f", times, g);
                var log = new List<string>();
                var r = g.doworkGPSOFFSET(logF, d, 0f, "GPS", false, log.Add);
                addMsgs("F-gps-gap", log);
                for (int i = 0; i < gaps.Length; i++)
                {
                    string f = Path.Combine(d, "IMG_" + (i + 1).ToString("0000") + ".jpg");
                    PictureInformation p;
                    bool ok = r.TryGetValue(f, out p);
                    res.AppendFormat("F-gps-gap,{0},{1:o},{2},{3},{4},{5},{6},{7},{8},{9},nearest fix is {9} ms away\n", Path.GetFileName(f), times[i], ok,
                        ok ? p.Time.ToUniversalTime().ToString("o") : "", ok ? F(p.Lat) : "", ok ? F(p.Lon) : "", ok ? F(p.AltAMSL) : "", ok ? F(p.RelAlt) : "",
                        ok ? F((p.Time.ToUniversalTime() - times[i]).TotalMilliseconds) : "", gaps[i]);
                }
            }
            Console.WriteLine("SIDE_EFFECT_XML_NEXT_TO_LOG={0}", File.Exists(logA + ".xml"));

            File.WriteAllText(Path.Combine(outDir, "georef-results.csv"), res.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(outDir, "georef-messages.csv"), msgs.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
