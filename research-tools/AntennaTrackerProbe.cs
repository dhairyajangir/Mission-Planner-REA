// Library-level probe of the original Mission Planner 1.3.83 antenna-tracker maths and output drivers.
// Part 1 reads CurrentState.AZToMAV / ELToMAV / DistToHome for fixed tracker and vehicle positions.
// Part 2 runs the Maestro, ArduTracker and DegreeTracker drivers against an in-memory serial port (no hardware,
// no real COM port, no vehicle, no network) and records the bytes they write.
// Usage: AntennaTrackerProbe.exe <dir with original MissionPlanner DLLs> <output dir>
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using MissionPlanner;
using MissionPlanner.Antenna;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;

sealed class CaptureSerial : ICommsSerial
{
    public readonly List<byte> Written = new List<byte>();
    public bool IsOpen { get; private set; }
    public Stream BaseStream { get { return Stream.Null; } }
    public int BaudRate { get; set; }
    public int BytesToRead { get { return 0; } }
    public int BytesToWrite { get { return 0; } }
    public int DataBits { get; set; }
    public bool DtrEnable { get; set; }
    public string PortName { get; set; }
    public int ReadBufferSize { get; set; }
    public int ReadTimeout { get; set; }
    public bool RtsEnable { get; set; }
    public int WriteBufferSize { get; set; }
    public int WriteTimeout { get; set; }
    public void Open() { IsOpen = true; }
    public void Close() { IsOpen = false; }
    public void Dispose() { }
    public void DiscardInBuffer() { }
    public int Read(byte[] buffer, int offset, int count) { return 0; }
    public int ReadByte() { return -1; }
    public int ReadChar() { return -1; }
    public string ReadExisting() { return ""; }
    public string ReadLine() { return ""; }
    public void Write(string text) { Written.AddRange(Encoding.ASCII.GetBytes(text)); }
    public void Write(byte[] buffer, int offset, int count) { for (int i = 0; i < count; i++) Written.Add(buffer[offset + i]); }
    public void WriteLine(string text) { Write(text + "\n"); }
    public void toggleDTR() { }
}

public static class AntennaTrackerProbe
{
    static readonly CultureInfo IC = CultureInfo.InvariantCulture;
    static string F(double v) { return v.ToString("R", IC); }

    public static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string p = Path.Combine(dir, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        return Run(Path.GetFullPath(args[1]));
    }

    // spherical truth for comparison: initial bearing and haversine ground distance
    static void Truth(double lat1, double lon1, double lat2, double lon2, out double bearing, out double dist)
    {
        double r = 6371008.8, d2r = Math.PI / 180;
        double p1 = lat1 * d2r, p2 = lat2 * d2r, dl = (lon2 - lon1) * d2r;
        double y = Math.Sin(dl) * Math.Cos(p2), x = Math.Cos(p1) * Math.Sin(p2) - Math.Sin(p1) * Math.Cos(p2) * Math.Cos(dl);
        bearing = (Math.Atan2(y, x) / d2r + 360) % 360;
        double a = Math.Pow(Math.Sin((p2 - p1) / 2), 2) + Math.Cos(p1) * Math.Cos(p2) * Math.Pow(Math.Sin(dl / 2), 2);
        dist = 2 * r * Math.Asin(Math.Min(1, Math.Sqrt(a)));
    }

    static void Offset(double lat, double lon, double bearingDeg, double meters, out double lat2, out double lon2)
    {
        double r = 6371008.8, d2r = Math.PI / 180, br = bearingDeg * d2r, dr = meters / r;
        double p1 = lat * d2r, l1 = lon * d2r;
        double p2 = Math.Asin(Math.Sin(p1) * Math.Cos(dr) + Math.Cos(p1) * Math.Sin(dr) * Math.Cos(br));
        double l2 = l1 + Math.Atan2(Math.Sin(br) * Math.Sin(dr) * Math.Cos(p1), Math.Cos(dr) - Math.Sin(p1) * Math.Sin(p2));
        lat2 = p2 / d2r; lon2 = l2 / d2r;
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string outDir)
    {
        try
        {
            Directory.CreateDirectory(outDir);
            var geo = new StringBuilder("case,tracker_lat,tracker_lng,tracker_alt,mav_lat,mav_lng,mav_alt,az,el,dist,truth_az,truth_ground_dist,az_err_deg\n");
            var sites = new[]
            {
                Tuple.Create("cmac", -35.3632621, 149.1652374, 584.0),
                Tuple.Create("zurich", 47.3977419, 8.5455938, 408.0),
                Tuple.Create("lat70", 70.0, 25.0, 10.0),
                Tuple.Create("equator", 0.0, 30.0, 10.0),
                Tuple.Create("lng0", 51.4779, 0.0, 10.0),
            };
            int n = 0;
            foreach (var site in sites)
                foreach (double dist in new[] { 500.0, 20000.0 })
                    foreach (double brg in new[] { 0.0, 45, 90, 135, 180, 225, 270, 315 })
                        foreach (double dz in new[] { 0.0, 100, -50 })
                        {
                            if (dist == 20000.0 && dz != 0) continue;
                            double mlat, mlng; Offset(site.Item2, site.Item3, brg, dist, out mlat, out mlng);
                            var cs = new CurrentState();
                            cs.TrackerLocation = new PointLatLngAlt(site.Item2, site.Item3, site.Item4);
                            cs.lat = mlat; cs.lng = mlng; cs.altasl = (float)(site.Item4 + dz);
                            double tb, td; Truth(site.Item2, site.Item3, mlat, mlng, out tb, out td);
                            double err = ((cs.AZToMAV - tb + 540) % 360) - 180;
                            geo.AppendFormat("{0}-{1}-b{2}-dz{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14},{15}\n", site.Item1, dist, brg, dz,
                                F(site.Item2), F(site.Item3), F(site.Item4), F(mlat), F(mlng), F(site.Item4 + dz),
                                F(cs.AZToMAV), F(cs.ELToMAV), F(cs.DistToHome), F(tb), F(td), F(err));
                            n++;
                        }
            // degenerate positions
            Action<string, double, double, double, double, double, double> edge = (name, tl, tg, ta, ml, mg, ma) =>
            {
                var cs = new CurrentState();
                cs.TrackerLocation = new PointLatLngAlt(tl, tg, ta);
                cs.lat = ml; cs.lng = mg; cs.altasl = (float)ma;
                geo.AppendFormat("edge-{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},,,\n", name, F(tl), F(tg), F(ta), F(ml), F(mg), F(ma), F(cs.AZToMAV), F(cs.ELToMAV), F(cs.DistToHome));
                n++;
            };
            edge("same-position", -35.0, 149.0, 100, -35.0, 149.0, 100);
            edge("vehicle-at-0-0", -35.0, 149.0, 100, 0, 0, 200);
            edge("antimeridian", 10.0, 179.999, 0, 10.0, -179.999, 0);
            edge("directly-above", -35.0, 149.0, 0, -35.0, 149.0, 500);
            edge("tracker-lng0-falls-back-to-home", 51.0, 0.0, 0, 51.001, 0.001, 0);
            File.WriteAllText(Path.Combine(outDir, "tracker-geometry.csv"), geo.ToString(), new UTF8Encoding(false));
            Console.WriteLine("GEOMETRY_ROWS=" + n);

            // part 2: output drivers on an in-memory serial port
            var outp = new StringBuilder("driver,config,pan,tilt,bytes_hex,decoded\n");
            double[] pans = { 0, 45, 90, 135, 179, 180, 181, 270, 359.9, 360, -10 };
            double[] tilts = { -20, 0, 10, 45, 60, 90 };
            var configs = new[]
            {
                new { Name = "pan360-tilt90", PanR = 360, TiltR = 90, TrimPan = 0.0, TrimTilt = 0.0, Rev = false },
                new { Name = "pan360-tilt90-trim20-5-rev", PanR = 360, TiltR = 90, TrimPan = 20.0, TrimTilt = 5.0, Rev = true },
                new { Name = "pan360-tilt180", PanR = 360, TiltR = 180, TrimPan = 0.0, TrimTilt = 0.0, Rev = false },
                new { Name = "pan360-tilt360", PanR = 360, TiltR = 360, TrimPan = 0.0, TrimTilt = 0.0, Rev = false },
            };
            Func<string, ITrackerOutput> make = d => d == "Maestro" ? (ITrackerOutput)new Maestro() : d == "ArduTracker" ? (ITrackerOutput)new ArduTracker() : new DegreeTracker();
            int rows = 0;
            foreach (var driver in new[] { "Maestro", "ArduTracker", "DegreeTracker" })
                foreach (var c in configs)
                {
                    var cap = new CaptureSerial();
                    var port = new MissionPlanner.Comms.SerialPort();
                    port._baseport = cap;
                    var t = make(driver);
                    t.ComPort = port;
                    t.PanStartRange = -c.PanR / 2; t.PanEndRange = c.PanR / 2;
                    t.TiltStartRange = -c.TiltR / 2; t.TiltEndRange = c.TiltR / 2;
                    t.TrimPan = c.TrimPan; t.TrimTilt = c.TrimTilt;
                    t.PanReverse = c.Rev; t.TiltReverse = c.Rev;
                    t.PanPWMRange = 1000; t.TiltPWMRange = 1000; t.PanPWMCenter = 1500; t.TiltPWMCenter = 1500;
                    t.PanSpeed = 20; t.TiltSpeed = 20; t.PanAccel = 5; t.TiltAccel = 5;
                    if (!t.Init()) throw new InvalidOperationException(driver + " Init failed");
                    cap.Written.Clear();
                    t.Setup();
                    outp.AppendFormat("{0},{1},setup,,{2},\"{3}\"\n", driver, c.Name, Hex(cap.Written), Decode(driver, cap.Written));
                    foreach (double pan in pans)
                        foreach (double tilt in tilts)
                        {
                            cap.Written.Clear();
                            string err = "";
                            try { t.PanAndTilt(pan, tilt); } catch (Exception ex) { err = " EXCEPTION " + ex.GetType().Name; }
                            outp.AppendFormat("{0},{1},{2},{3},{4},\"{5}{6}\"\n", driver, c.Name, F(pan), F(tilt), Hex(cap.Written), Decode(driver, cap.Written), err);
                            rows++;
                        }
                }
            File.WriteAllText(Path.Combine(outDir, "tracker-output.csv"), outp.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            Console.WriteLine("DRIVER_ROWS=" + rows);
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }

    static string Hex(List<byte> b)
    {
        var sb = new StringBuilder();
        foreach (var x in b) sb.Append(x.ToString("X2"));
        return sb.ToString();
    }

    // Maestro: repeated 0x84/0x87/0x89, address, 14-bit value (low 7 bits first). Others: ASCII.
    static string Decode(string driver, List<byte> b)
    {
        if (driver != "Maestro") return Encoding.ASCII.GetString(b.ToArray()).Replace("\n", "\\n");
        var sb = new StringBuilder();
        for (int i = 0; i + 3 < b.Count; i += 4)
        {
            int value = b[i + 2] | (b[i + 3] << 7);
            sb.AppendFormat("{0}:ch{1}={2}{3} ", b[i] == 0x84 ? "target" : b[i] == 0x87 ? "speed" : b[i] == 0x89 ? "accel" : "cmd" + b[i].ToString("X2"),
                b[i + 1], b[i] == 0x84 ? (value / 4.0).ToString("0.##", IC) + "us" : value.ToString(IC), "");
        }
        return sb.ToString().Trim();
    }
}
