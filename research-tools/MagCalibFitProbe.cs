// Library-level probe of the original Mission Planner 1.3.83 MagCalib least-squares fit (legacy offboard compass
// calibration). Pure numerics on synthetic data: no vehicle, link, simulator or log file. It calls the compiled
// MagCalib.LeastSq and the private RemoveOutliers (via reflection) and compares results with the known truth.
// Usage: MagCalibFitProbe.exe <dir with original MissionPlanner DLLs> <output dir>
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using MissionPlanner;

public static class MagCalibFitProbe
{
    static readonly CultureInfo IC = CultureInfo.InvariantCulture;
    static string F(double v) { return v.ToString("R", IC); }

    sealed class Spec
    {
        public string Id; public double Radius = 500; public double[] Center = { 0, 0, 0 };
        public double[] Scale = { 1, 1, 1 }; public double Sigma = 0; public bool Hemisphere = false; public int N = 400; public int Seed = 7;
    }

    // Fibonacci sphere points, optional hemisphere (z > 0), per-axis distortion, centre shift and Gaussian noise.
    static List<Tuple<float, float, float>> Generate(Spec s)
    {
        var rnd = new Random(s.Seed);
        var list = new List<Tuple<float, float, float>>();
        double golden = Math.PI * (3 - Math.Sqrt(5));
        for (int i = 0; i < s.N; i++)
        {
            double z = s.Hemisphere ? 1 - (i + 0.5) / s.N : 1 - 2 * (i + 0.5) / s.N;
            double r = Math.Sqrt(Math.Max(0, 1 - z * z)), phi = i * golden;
            double[] p = { r * Math.Cos(phi), r * Math.Sin(phi), z };
            double[] v = new double[3];
            for (int k = 0; k < 3; k++)
            {
                double noise = s.Sigma == 0 ? 0 : s.Sigma * Math.Sqrt(-2 * Math.Log(1 - rnd.NextDouble())) * Math.Cos(2 * Math.PI * rnd.NextDouble());
                v[k] = s.Radius * p[k] * s.Scale[k] + s.Center[k] + noise;
            }
            list.Add(Tuple.Create((float)v[0], (float)v[1], (float)v[2]));
        }
        return list;
    }

    // ArduPilot convention: corrected = M * (raw + offsets), M = [[dx,ox,oy],[ox,dy,oz],[oy,oz,dz]].
    static void Corrected(List<Tuple<float, float, float>> data, double[] x, out double mean, out double spreadPct)
    {
        bool full = x.Length >= 9;
        double dx = full ? x[3] : 1, dy = full ? x[4] : 1, dz = full ? x[5] : 1;
        double ox = full ? x[6] : 0, oy = full ? x[7] : 0, oz = full ? x[8] : 0;
        double sum = 0, sum2 = 0;
        foreach (var d in data)
        {
            double a = d.Item1 + x[0], b = d.Item2 + x[1], c = d.Item3 + x[2];
            double m1 = dx * a + ox * b + oy * c, m2 = ox * a + dy * b + oz * c, m3 = oy * a + oz * b + dz * c;
            double len = Math.Sqrt(m1 * m1 + m2 * m2 + m3 * m3);
            sum += len; sum2 += len * len;
        }
        int n = data.Count;
        mean = sum / n;
        spreadPct = 100 * Math.Sqrt(Math.Max(0, sum2 / n - mean * mean)) / mean;
    }

    public static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string p = Path.Combine(dir, new AssemblyName(e.Name).Name + ".dll");
            if (!File.Exists(p)) p = Path.Combine(dir, new AssemblyName(e.Name).Name + ".exe");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        return Run(Path.GetFullPath(args[1]));
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string outDir)
    {
        try
        {
            Directory.CreateDirectory(outDir);
            var bf = BindingFlags.NonPublic | BindingFlags.Static;
            var removeOutliers = typeof(MagCalib).GetMethod("RemoveOutliers", bf);
            var radField = typeof(MagCalib).GetField("rad", bf);
            if (removeOutliers == null || radField == null) throw new InvalidOperationException("private members not found");

            var specs = new List<Spec>
            {
                new Spec { Id = "s0-centered" },
                new Spec { Id = "s1-offset-clean", Center = new[] { 120.0, -80, 40 } },
                new Spec { Id = "s2-offset-noise5", Center = new[] { 120.0, -80, 40 }, Sigma = 5 },
                new Spec { Id = "s3-bigoffset-noise5", Center = new[] { 400.0, -300, 250 }, Sigma = 5 },
                new Spec { Id = "s4-hemisphere-noise5", Center = new[] { 120.0, -80, 40 }, Sigma = 5, Hemisphere = true },
                new Spec { Id = "e1-distorted-noise5", Center = new[] { 120.0, -80, 40 }, Scale = new[] { 1.15, 0.9, 1.0 }, Sigma = 5 },
            };

            var data = new StringBuilder("case,idx,x,y,z\n");
            var res = new StringBuilder("case,stage,n_used,ofs_x,ofs_y,ofs_z,fit_r,dia_x,dia_y,dia_z,odi_x,odi_y,odi_z,mag_rad,truth_ofs_x,truth_ofs_y,truth_ofs_z,ofs_err,corrected_mean,corrected_spread_pct\n");
            foreach (var s in specs)
            {
                var raw = Generate(s);
                for (int i = 0; i < raw.Count; i++)
                    data.AppendFormat("{0},{1},{2},{3},{4}\n", s.Id, i, F(raw[i].Item1), F(raw[i].Item2), F(raw[i].Item3));
                foreach (bool outliers in new[] { false, true })
                    foreach (bool ellipsoid in new[] { false, true })
                    {
                        var work = new List<Tuple<float, float, float>>(raw);
                        if (outliers) removeOutliers.Invoke(null, new object[] { work });
                        double[] x = MagCalib.LeastSq(work, ellipsoid);
                        double rad = (double)radField.GetValue(null);
                        double mean, spread;
                        Corrected(raw, x, out mean, out spread);   // evaluated on the full, unfiltered data
                        double e = Math.Sqrt(Math.Pow(x[0] + s.Center[0], 2) + Math.Pow(x[1] + s.Center[1], 2) + Math.Pow(x[2] + s.Center[2], 2));
                        string stage = (ellipsoid ? "ellipsoid" : "sphere") + (outliers ? "+outliers" : "");
                        Func<int, string> at = i => x.Length > i ? F(x[i]) : "";
                        res.AppendFormat("{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14},{15},{16},{17},{18},{19}\n",
                            s.Id, stage, work.Count, F(x[0]), F(x[1]), F(x[2]), x.Length == 4 ? F(x[3]) : "",
                            x.Length >= 9 ? F(x[3]) : "", at(4).Length > 0 && x.Length >= 9 ? at(4) : "", x.Length >= 9 ? at(5) : "",
                            x.Length >= 9 ? at(6) : "", x.Length >= 9 ? at(7) : "", x.Length >= 9 ? at(8) : "",
                            F(rad), F(-s.Center[0]), F(-s.Center[1]), F(-s.Center[2]), F(e), F(mean), F(spread));
                        Console.WriteLine("{0,-22} {1,-18} n={2,-4} ofs=({3:F1},{4:F1},{5:F1}) err={6:F2} corrected spread={7:F2}%",
                            s.Id, stage, work.Count, x[0], x[1], x[2], e, spread);
                    }
            }

            // RemoveOutliers count behaviour on lists with increasing distance from the origin.
            var rem = new StringBuilder("list_size,removed,largest_kept_dist,smallest_removed_dist\n");
            foreach (int n in new[] { 15, 16, 17, 31, 32, 100, 400 })
            {
                var l = new List<Tuple<float, float, float>>();
                for (int i = 0; i < n; i++) l.Add(Tuple.Create((float)(i + 1), 0f, 0f));
                l.Reverse(); // unsorted input
                var before = new List<Tuple<float, float, float>>(l);
                removeOutliers.Invoke(null, new object[] { l });
                double maxKept = 0, minRemoved = double.MaxValue;
                foreach (var t in l) maxKept = Math.Max(maxKept, t.Item1);
                foreach (var t in before) if (!l.Contains(t)) minRemoved = Math.Min(minRemoved, t.Item1);
                rem.AppendFormat("{0},{1},{2},{3}\n", n, n - l.Count, F(maxKept), minRemoved == double.MaxValue ? "" : F(minRemoved));
            }

            File.WriteAllText(Path.Combine(outDir, "mag-fit-data.csv"), data.ToString(), new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(outDir, "mag-fit-results.csv"), res.ToString(), new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(outDir, "mag-fit-outliers.csv"), rem.ToString(), new UTF8Encoding(false));
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
