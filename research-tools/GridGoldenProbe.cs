// Library-level probe of the original Mission Planner 1.3.83 Utilities.Grid.CreateGrid. Pure geometry: no vehicle, link,
// simulator or network. Records what the compiled library returns for fixed polygons and parameter variations, plus a
// few degenerate inputs, as golden CSV files. It captures behaviour; it does not judge whether a plan is good.
// Usage: GridGoldenProbe.exe <dir with original MissionPlanner DLLs> <output dir>
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using MissionPlanner.Utilities;

sealed class GridCase
{
    public string Id, Site, Poly;
    public double Alt = 100, Dist = 40, Spacing = 40, Angle = 0, Over1 = 0, Over2 = 0;
    public Grid.StartPosition Start = Grid.StartPosition.BottomLeft;
    public bool Shutter = false, Ext = true;
    public float MinLane = 0, Lead1 = 0, Lead2 = 0;
    public bool UsePointStart = false;
    public GridCase Clone(string suffix, Action<GridCase> edit)
    {
        var c = (GridCase)MemberwiseClone();
        c.Id = Id + "-" + suffix;
        edit(c);
        return c;
    }
}

public static class GridGoldenProbe
{
    static readonly CultureInfo IC = CultureInfo.InvariantCulture;
    static readonly Dictionary<string, double[]> Sites = new Dictionary<string, double[]>
    {
        { "cmac", new[] { -35.3632621, 149.1652374 } },   // ArduPilot SITL default location (southern hemisphere)
        { "zurich", new[] { 47.3977419, 8.5455938 } },    // northern hemisphere, UTM zone 32
    };
    // local metres (east, north) from the site origin
    static readonly Dictionary<string, double[][]> Shapes = new Dictionary<string, double[][]>
    {
        { "rect", new[] { P(0, 0), P(240, 0), P(240, 160), P(0, 160) } },
        { "rect_closed", new[] { P(0, 0), P(240, 0), P(240, 160), P(0, 160), P(0, 0) } },
        { "lshape", new[] { P(0, 0), P(240, 0), P(240, 80), P(120, 80), P(120, 200), P(0, 200) } },
        { "ushape", new[] { P(0, 0), P(240, 0), P(240, 160), P(160, 160), P(160, 50), P(80, 50), P(80, 160), P(0, 160) } },
        { "tri", new[] { P(0, 0), P(220, 30), P(100, 180) } },
        { "quad", new[] { P(0, 25), P(210, 0), P(260, 150), P(30, 190) } },
    };
    static double[] P(double e, double n) { return new[] { e, n }; }

    static string F(double v) { return v.ToString("R", IC); }

    static List<PointLatLngAlt> Polygon(string site, string shape)
    {
        var o = Sites[site];
        var list = new List<PointLatLngAlt>();
        foreach (var p in Shapes[shape])
        {
            double lat = o[0] + p[1] / 111320.0;
            double lng = o[1] + p[0] / (111320.0 * Math.Cos(o[0] * Math.PI / 180.0));
            list.Add(new PointLatLngAlt(lat, lng, 0, ""));
        }
        return list;
    }

    static PointLatLngAlt Offset(string site, double e, double n)
    {
        var o = Sites[site];
        return new PointLatLngAlt(o[0] + n / 111320.0, o[1] + e / (111320.0 * Math.Cos(o[0] * Math.PI / 180.0)), 0, "");
    }

    static List<GridCase> BuildCases()
    {
        var cases = new List<GridCase>();
        foreach (var shape in new[] { "rect", "ushape", "lshape", "tri", "quad", "rect_closed" })
        {
            var b = new GridCase { Id = "cmac-" + shape, Site = "cmac", Poly = shape };
            cases.Add(b);
            foreach (var a in new[] { 15.0, 45.0, 90.0, 135.0, 200.0, 359.9 })
                cases.Add(b.Clone("angle" + a.ToString(IC), c => c.Angle = a));
            cases.Add(b.Clone("start-home", c => c.Start = Grid.StartPosition.Home));
            cases.Add(b.Clone("start-topright", c => c.Start = Grid.StartPosition.TopRight));
            cases.Add(new GridCase { Id = "zurich-" + shape, Site = "zurich", Poly = shape });
        }
        foreach (var shape in new[] { "rect", "ushape" })
        {
            var b = new GridCase { Id = "cmac-" + shape, Site = "cmac", Poly = shape };
            cases.Add(b.Clone("dist15", c => c.Dist = 15));
            cases.Add(b.Clone("dist90", c => c.Dist = 90));
            cases.Add(b.Clone("spacing0", c => c.Spacing = 0));
            cases.Add(b.Clone("spacing15", c => c.Spacing = 15));
            cases.Add(b.Clone("over1-neg8", c => c.Over1 = -8));
            cases.Add(b.Clone("over1-10", c => c.Over1 = 10));
            cases.Add(b.Clone("over2-neg8", c => c.Over2 = -8));
            cases.Add(b.Clone("over2-10", c => c.Over2 = 10));
            cases.Add(b.Clone("lead1-neg8", c => c.Lead1 = -8));
            cases.Add(b.Clone("lead1-8", c => c.Lead1 = 8));
            cases.Add(b.Clone("lead2-neg8", c => c.Lead2 = -8));
            cases.Add(b.Clone("lead2-8", c => c.Lead2 = 8));
            cases.Add(b.Clone("start-topleft", c => c.Start = Grid.StartPosition.TopLeft));
            cases.Add(b.Clone("start-bottomright", c => c.Start = Grid.StartPosition.BottomRight));
            cases.Add(b.Clone("start-point", c => { c.Start = Grid.StartPosition.Point; c.UsePointStart = true; }));
            cases.Add(b.Clone("minlane1-dist15", c => { c.Dist = 15; c.MinLane = 1; }));
            cases.Add(b.Clone("minlane3-dist15", c => { c.Dist = 15; c.MinLane = 3; }));
            cases.Add(b.Clone("minlane3-dist15-noext", c => { c.Dist = 15; c.MinLane = 3; c.Ext = false; }));
            cases.Add(b.Clone("noext", c => c.Ext = false));
            cases.Add(b.Clone("shutter", c => c.Shutter = true));
            cases.Add(b.Clone("alt50.5", c => c.Alt = 50.5));
        }
        return cases;
    }

    static List<PointLatLngAlt> Run(GridCase c, List<PointLatLngAlt> poly)
    {
        Grid.StartPointLatLngAlt = c.UsePointStart ? Offset(c.Site, 300, 120) : PointLatLngAlt.Zero;
        var home = Offset(c.Site, -50, -50);
        return Grid.CreateGrid(poly, c.Alt, c.Dist, c.Spacing, c.Angle, c.Over1, c.Over2, c.Start, c.Shutter,
            c.MinLane, c.Lead1, c.Lead2, home, c.Ext);
    }

    public static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string p = Path.Combine(dir, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        int rc = Go(Path.GetFullPath(args[1]));
        Environment.Exit(rc); // abandoned timed-out edge-case threads must not keep the process alive
        return rc;
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Go(string outDir)
    {
        try
        {
            Directory.CreateDirectory(outDir);
            var polys = new StringBuilder("site,polygon,idx,lat,lng\n");
            foreach (var site in Sites.Keys)
                foreach (var shape in Shapes.Keys)
                {
                    var pl = Polygon(site, shape);
                    for (int i = 0; i < pl.Count; i++)
                        polys.AppendFormat("{0},{1},{2},{3},{4}\n", site, shape, i, F(pl[i].Lat), F(pl[i].Lng));
                }
            var cases = new StringBuilder("case_id,site,polygon,alt,dist,spacing,angle,over1,over2,start,shutter,minlane,lead1,lead2,ext,point_start,points,error\n");
            var points = new StringBuilder("case_id,idx,tag,lat,lng,alt\n");
            int total = 0, nondeterministic = 0, errors = 0;
            foreach (var c in BuildCases())
            {
                var poly = Polygon(c.Site, c.Poly);
                List<PointLatLngAlt> a = null, b = null;
                string err = "";
                try { a = Run(c, poly); b = Run(c, Polygon(c.Site, c.Poly)); }
                catch (Exception ex) { err = ex.GetType().Name + ": " + ex.Message.Replace(',', ';').Replace('\n', ' '); errors++; }
                int n = a == null ? 0 : a.Count;
                if (a != null && b != null)
                {
                    bool same = a.Count == b.Count;
                    for (int i = 0; same && i < a.Count; i++)
                        same = a[i].Lat == b[i].Lat && a[i].Lng == b[i].Lng && a[i].Alt == b[i].Alt && a[i].Tag == b[i].Tag;
                    if (!same) { nondeterministic++; Console.WriteLine("NONDETERMINISTIC " + c.Id); }
                }
                cases.AppendFormat("{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14},{15},{16},{17}\n",
                    c.Id, c.Site, c.Poly, F(c.Alt), F(c.Dist), F(c.Spacing), F(c.Angle), F(c.Over1), F(c.Over2), c.Start,
                    c.Shutter ? 1 : 0, F(c.MinLane), F(c.Lead1), F(c.Lead2), c.Ext ? 1 : 0, c.UsePointStart ? 1 : 0, n, err);
                for (int i = 0; i < n; i++)
                    points.AppendFormat("{0},{1},{2},{3},{4},{5}\n", c.Id, i, a[i].Tag, F(a[i].Lat), F(a[i].Lng), F(a[i].Alt));
                total += n;
            }
            Write(outDir, "grid-polygons.csv", polys);
            Write(outDir, "grid-cases.csv", cases);
            Write(outDir, "grid-points.csv", points);
            Console.WriteLine("GRID_POINTS={0} NONDETERMINISTIC={1} CASE_ERRORS={2}", total, nondeterministic, errors);
            Write(outDir, "grid-edge-cases.csv", EdgeCases());
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }

    static void Write(string dir, string name, StringBuilder sb)
    {
        File.WriteAllText(Path.Combine(dir, name), sb.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
    }

    static StringBuilder EdgeCases()
    {
        var sb = new StringBuilder("name,points,elapsed_ms,outcome\n");
        var rect = Polygon("cmac", "rect");
        var home = Offset("cmac", -50, -50);
        Func<double, double, double, PointLatLngAlt> pt = (e, n, z) => Offset("cmac", e, n);
        var edge = new List<KeyValuePair<string, Func<List<PointLatLngAlt>>>>();
        Action<string, Func<List<PointLatLngAlt>>> add = (n, f) => edge.Add(new KeyValuePair<string, Func<List<PointLatLngAlt>>>(n, f));
        Func<List<PointLatLngAlt>, double, double, Grid.StartPosition, PointLatLngAlt, List<PointLatLngAlt>> g =
            (poly, dist, spacing, start, h) => Grid.CreateGrid(poly, 100, dist, spacing, 0, 0, 0, start, false, 0, 0, 0, h, true);
        add("empty-polygon", () => g(new List<PointLatLngAlt>(), 40, 40, Grid.StartPosition.BottomLeft, home));
        add("one-point", () => g(new List<PointLatLngAlt> { pt(0, 0, 0) }, 40, 40, Grid.StartPosition.BottomLeft, home));
        add("two-points", () => g(new List<PointLatLngAlt> { pt(0, 0, 0), pt(200, 0, 0) }, 40, 40, Grid.StartPosition.BottomLeft, home));
        add("collinear-three", () => g(new List<PointLatLngAlt> { pt(0, 0, 0), pt(100, 0, 0), pt(200, 0, 0) }, 40, 40, Grid.StartPosition.BottomLeft, home));
        add("identical-four", () => g(new List<PointLatLngAlt> { pt(0, 0, 0), pt(0, 0, 0), pt(0, 0, 0), pt(0, 0, 0) }, 40, 40, Grid.StartPosition.BottomLeft, home));
        add("distance-0-clamped", () => g(rect, 0, 0, Grid.StartPosition.BottomLeft, home));
        add("distance-negative", () => g(rect, -5, 40, Grid.StartPosition.BottomLeft, home));
        add("spacing-0.05-clamped", () => g(rect, 40, 0.05, Grid.StartPosition.BottomLeft, home));
        add("distance-1e6", () => g(rect, 1e6, 40, Grid.StartPosition.BottomLeft, home));
        add("home-start-null-home", () => g(rect, 40, 40, Grid.StartPosition.Home, null));
        add("utm-zone-boundary", () =>
        {
            var z = new List<PointLatLngAlt>
            {
                new PointLatLngAlt(47.0, 5.9990, 0, ""), new PointLatLngAlt(47.0, 6.0030, 0, ""),
                new PointLatLngAlt(47.0015, 6.0030, 0, ""), new PointLatLngAlt(47.0015, 5.9990, 0, "")
            };
            return g(z, 40, 40, Grid.StartPosition.BottomLeft, new PointLatLngAlt(46.999, 5.998, 0, ""));
        });
        add("nan-latitude-vertex", () => g(new List<PointLatLngAlt> { new PointLatLngAlt(double.NaN, 149.1652374, 0, ""), pt(240, 0, 0), pt(240, 160, 0) }, 40, 40, Grid.StartPosition.BottomLeft, home));
        foreach (var kv in edge)
        {
            var sw = Stopwatch.StartNew();
            string outcome; int n = -1;
            var task = Task.Run(kv.Value);
            try
            {
                if (!task.Wait(20000)) outcome = "TIMEOUT>20s";
                else { n = task.Result.Count; outcome = "OK"; }
            }
            catch (AggregateException ex) { outcome = "EXCEPTION " + ex.GetBaseException().GetType().Name; }
            sb.AppendFormat("{0},{1},{2},{3}\n", kv.Key, n, sw.ElapsedMilliseconds, outcome);
            Console.WriteLine("EDGE {0} points={1} {2}ms {3}", kv.Key, n, sw.ElapsedMilliseconds, outcome);
        }
        return sb;
    }
}
