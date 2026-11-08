// Library-level probe of the PID class in Mission Planner 1.3.83's Swarm/Formation.cs (a port of an early ArduPilot
// AC_PID). Pure numerics: no vehicle, link, simulator, formation logic or network. The rest of the swarm code needs live
// vehicle state and was not run.
// Usage: SwarmPidProbe.exe <dir with original MissionPlanner DLLs> <output dir>
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using MissionPlanner.Swarm;

public static class SwarmPidProbe
{
    static readonly CultureInfo IC = CultureInfo.InvariantCulture;
    static string F(double v) { return v.ToString("R", IC); }

    public static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string n = new AssemblyName(e.Name).Name;
            string p = Path.Combine(dir, n + ".dll");
            if (!File.Exists(p)) p = Path.Combine(dir, n + ".exe");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        return Run(Path.GetFullPath(args[1]));
    }

    static readonly StringBuilder Rows = new StringBuilder("case,tick,input,p,i,d,pid\n");

    // one tick: feed the filter, then read the terms in the order the formation code does (p, i, d)
    static float Tick(string name, int tick, PID pid, float input, bool getPidOnly = false, bool callIFirst = false)
    {
        pid.set_input_filter_all(input);
        if (callIFirst) pid.get_i();     // an extra, unrelated call to get_i
        float p = pid.get_p(), i = getPidOnly ? 0 : pid.get_i(), d = pid.get_d();
        Rows.AppendFormat("{0},{1},{2},{3},{4},{5},{6}\n", name, tick, F(input), F(p), F(i), F(d), F(p + i + d));
        return p;
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string outDir)
    {
        try
        {
            Directory.CreateDirectory(outDir);
            var summary = new StringBuilder();

            // 1/2: step response, compared with the closed-form first-order filter value
            foreach (var cfg in new[] { new { Name = "step-dt0.1-20hz", Dt = 0.1f, Hz = 20f }, new { Name = "step-dt0.02-5hz", Dt = 0.02f, Hz = 5f } })
            {
                var pid = new PID(1f, 0.5f, 0.1f, 10f, cfg.Hz, cfg.Dt, 0f);
                double alpha = cfg.Dt / (cfg.Dt + 1.0 / (2 * Math.PI * cfg.Hz));
                double maxErr = 0;
                for (int t = 0; t < 60; t++)
                {
                    float input = t == 0 ? 0f : 1f;              // first sample is taken as-is (filter reset), then a unit step
                    float p = Tick(cfg.Name, t, pid, input);
                    double analytic = t == 0 ? 0 : 1 - Math.Pow(1 - alpha, t);
                    maxErr = Math.Max(maxErr, Math.Abs(p - analytic));
                }
                summary.AppendFormat("{0}: alpha={1:F6} max|P - closed-form filtered step|={2:E2}\n", cfg.Name, alpha, maxErr);
            }

            // 3: integrator limit and negative limit argument
            var lim = new PID(0f, 1f, 0f, 0.5f, 20f, 0.1f, 0f);
            for (int t = 0; t < 12; t++) Tick("imax-0.5-ki1", t, lim, t < 8 ? 1f : -1f);
            var neg = new PID(0f, 1f, 0f, -3f, 20f, 0.1f, 0f);
            for (int t = 0; t < 40; t++) Tick("imax-argument-negative-3", t, neg, 5f);

            // 4: filter frequency 0 (clamped to 0.01 Hz)
            var zero = new PID(1f, 0f, 0f, 1f, 0f, 0.1f, 0f);
            for (int t = 0; t < 6; t++) Tick("filt-hz-0-passed", t, zero, t == 0 ? 0f : 1f);
            summary.AppendFormat("filt_hz argument 0: alpha={0:E3} (a 20 Hz filter at dt 0.1 would be {1:F4})\n",
                zero.get_filt_alpha(), new PID(1, 0, 0, 1, 20f, 0.1f, 0).get_filt_alpha());

            // 5: non-finite input
            var inf = new PID(1f, 0.1f, 0.01f, 10f, 20f, 0.1f, 0f);
            float[] seq = { 1f, 1f, 1f, float.PositiveInfinity, 1f, float.NegativeInfinity, 1f };
            for (int t = 0; t < seq.Length; t++) Tick("infinity-input", t, inf, seq[t]);
            var nan = new PID(1f, 0.1f, 0.01f, 10f, 20f, 0.1f, 0f);
            float[] seqn = { 1f, 1f, 1f, float.NaN, 1f, 1f, 1f };
            for (int t = 0; t < seqn.Length; t++) Tick("nan-input", t, nan, seqn[t]);
            nan.reset_I();
            Tick("nan-input", 7, nan, 1f);
            summary.AppendFormat("after a NaN input and reset_I, P term is {0}\n", nan.get_p());

            // 6: get_i called twice per tick
            var once = new PID(0f, 1f, 0f, 100f, 20f, 0.1f, 0f);
            var twice = new PID(0f, 1f, 0f, 100f, 20f, 0.1f, 0f);
            for (int t = 0; t < 5; t++) { Tick("get_i-once", t, once, 1f); Tick("get_i-twice", t, twice, 1f, false, true); }

            // 7: dt of zero, then set_dt
            var dt0 = new PID(1f, 1f, 1f, 10f, 20f, 0f, 0f);
            for (int t = 0; t < 4; t++) Tick("dt-0", t, dt0, t == 0 ? 0f : 1f);
            dt0.set_dt(0.1f);
            for (int t = 4; t < 8; t++) Tick("dt-0-then-0.1", t, dt0, 1f);

            // 8: feed-forward and combined getters
            var ff = new PID(1f, 0f, 0f, 1f, 20f, 0.1f, 0.25f);
            summary.AppendFormat("get_ff(8) with ff=0.25: {0}\n", ff.get_ff(8f));

            File.WriteAllText(Path.Combine(outDir, "pid-cases.csv"), Rows.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(outDir, "pid-summary.txt"), summary.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            Console.Write(summary.ToString());
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
