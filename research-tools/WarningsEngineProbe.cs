// Library-level probe of the original Mission Planner 1.3.83 custom-warning engine (CustomWarning / WarningEngine).
// A fake data source object stands in for the vehicle state: no vehicle, link, speech engine, GUI or network.
// Usage: WarningsEngineProbe.exe <dir with original MissionPlanner DLLs> <output dir>
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
using MissionPlanner.Utilities;
using MissionPlanner.Warnings;

public enum FakeMode { Stabilize = 0, Auto = 3, Rtl = 6 }

public sealed class FakeSource
{
    public double Voltage { get; set; }
    public int Sats { get; set; }
    public float Alt { get; set; }
    public bool Armed { get; set; }
    public string ModeName { get; set; }
    public FakeMode Mode { get; set; }
    public string Unset { get; set; }          // stays null: skipped by GetOptions
    public double Value { get; set; }
}

public static class WarningsEngineProbe
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
        int rc = Run(Path.GetFullPath(args[1]));
        Environment.Exit(rc); // the static engine loop is a background task; do not wait for it
        return rc;
    }

    static CustomWarning Make(string field, CustomWarning.Conditional cond, double threshold, int repeat = 10)
    {
        var w = new CustomWarning { ConditionType = cond, Warning = threshold, RepeatTime = repeat };
        w.SetField(field);
        return w;
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string outDir)
    {
        try
        {
            Directory.CreateDirectory(outDir);
            var src = new FakeSource { Voltage = 11.1, Sats = 8, Alt = 100f, Armed = true, ModeName = "AUTO", Mode = FakeMode.Auto, Value = 10 };
            CustomWarning.defaultsrc = src;

            // A: threshold semantics per condition and value, plus property types
            var a = new StringBuilder("field,type,condition,threshold,value,result\n");
            foreach (CustomWarning.Conditional cond in Enum.GetValues(typeof(CustomWarning.Conditional)))
                foreach (double v in new[] { 4.9, 5.0, 5.1 })
                {
                    src.Value = v;
                    var w = Make("Value", cond, 5.0);
                    a.AppendFormat("Value,double,{0},5,{1},{2}\n", cond, F(v), w.CheckValue(false));
                }
            src.Value = double.NaN;
            foreach (CustomWarning.Conditional cond in Enum.GetValues(typeof(CustomWarning.Conditional)))
                a.AppendFormat("Value,double,{0},5,NaN,{1}\n", cond, Make("Value", cond, 5.0).CheckValue(false));
            src.Value = 0.1 + 0.2;   // 0.30000000000000004
            a.AppendFormat("Value,double,EQ,0.3,0.1+0.2,{0}\n", Make("Value", CustomWarning.Conditional.EQ, 0.3).CheckValue(false));
            src.Alt = 0.1f;          // float widened to double
            a.AppendFormat("Alt,float,EQ,0.1,0.1f,{0}\n", Make("Alt", CustomWarning.Conditional.EQ, 0.1).CheckValue(false));
            foreach (var field in new[] { "Sats", "Armed", "Mode", "ModeName" })
            {
                string result;
                try { result = Make(field, CustomWarning.Conditional.GT, 0.5).CheckValue(false).ToString(); }
                catch (Exception ex) { result = "EXCEPTION " + ex.GetType().Name; }
                a.AppendFormat("{0},{1},GT,0.5,{2},{3}\n", field, field == "Sats" ? "int" : field == "Armed" ? "bool" : field == "Mode" ? "enum" : "string",
                    field == "Sats" ? "8" : field == "Armed" ? "true" : field == "Mode" ? "Auto(3)" : "AUTO", result);
            }
            var options = new CustomWarning().GetOptions();
            File.WriteAllText(Path.Combine(outDir, "warnings-threshold.csv"), a.ToString(), new UTF8Encoding(false));
            Console.WriteLine("OPTIONS=" + string.Join("|", options));
            try { Make("Missing", CustomWarning.Conditional.GT, 1); Console.WriteLine("SETFIELD_MISSING=no exception"); }
            catch (Exception ex) { Console.WriteLine("SETFIELD_MISSING=" + ex.GetType().Name); }

            // B: SayText formatting
            var b = new StringBuilder("culture,threshold,value,text\n");
            var template = "WARNING: {name} is {value} (limit {warning}) {value}";
            foreach (var cultureName in new[] { "invariant", "en-US", "de-DE" })
            {
                Thread.CurrentThread.CurrentCulture = cultureName == "invariant" ? CultureInfo.InvariantCulture : new CultureInfo(cultureName);
                foreach (double[] tv in new[] { new[] { 5.0, 12.345 }, new[] { 0.125, 0.004 }, new[] { 1e6, -0.5 }, new[] { 3.14159, double.NaN } })
                {
                    src.Voltage = tv[1];
                    var w = Make("Voltage", CustomWarning.Conditional.GT, tv[0]);
                    w.Text = template;
                    b.AppendFormat("{0},{1},{2},\"{3}\"\n", cultureName, F(tv[0]), F(tv[1]), w.SayText());
                }
            }
            Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
            File.WriteAllText(Path.Combine(outDir, "warnings-saytext.csv"), b.ToString(), new UTF8Encoding(false));

            // C: repeat suppression (RepeatTime = 1 s, condition always true)
            src.Value = 10;
            var c = new StringBuilder("t_ms,result\n");
            var wr = Make("Value", CustomWarning.Conditional.GT, 5, 1);
            var sw = Stopwatch.StartNew();
            foreach (int at in new[] { 0, 300, 900, 1100, 1300, 2200 })
            {
                while (sw.ElapsedMilliseconds < at) Thread.Sleep(5);
                c.AppendFormat("{0},{1}\n", at, wr.CheckValue());
            }
            File.WriteAllText(Path.Combine(outDir, "warnings-repeat.csv"), c.ToString(), new UTF8Encoding(false));

            // D: parent/child chain through the private checkCond. Parent: Value > 5, child: Sats > 6; RepeatTime 2 s.
            var check = typeof(WarningEngine).GetMethod("checkCond", BindingFlags.NonPublic | BindingFlags.Static);
            var d = new StringBuilder("t_ms,value,sats,result\n");
            var parent = Make("Value", CustomWarning.Conditional.GT, 5, 2);
            parent.Child = Make("Sats", CustomWarning.Conditional.GT, 6, 2);
            sw.Restart();
            src.Value = 10; src.Sats = 3;                   // parent true, child false
            Func<bool> go = () => (bool)check.Invoke(null, new object[] { parent });
            d.AppendFormat("0,10,3,{0}\n", go());
            Thread.Sleep(300);
            src.Sats = 8;                                   // child now true, inside parent's repeat window
            d.AppendFormat("{0},10,8,{1}\n", sw.ElapsedMilliseconds, go());
            while (sw.ElapsedMilliseconds < 2200) Thread.Sleep(10);
            d.AppendFormat("{0},10,8,{1}\n", sw.ElapsedMilliseconds, go());
            File.WriteAllText(Path.Combine(outDir, "warnings-chain.csv"), d.ToString(), new UTF8Encoding(false));

            // E: engine loop. A colouring warning and a speak/text warning, condition always true; event log with timestamps.
            var events = new List<string>();
            var elock = new object();
            Stopwatch esw = Stopwatch.StartNew();
            WarningEngine.QuickPanelColoring += (name, color) => { lock (elock) events.Add(string.Format("{0},colour,{1},{2}", esw.ElapsedMilliseconds, name, color)); };
            EventHandler<string> msg = (s, text) => { lock (elock) events.Add(string.Format("{0},message,,{1}", esw.ElapsedMilliseconds, text)); };
            WarningEngine.WarningMessage += msg;
            src.Value = 10; src.Sats = 8;
            lock (WarningEngine.warnings)
            {
                WarningEngine.warnings.Clear();
                var colour = Make("Value", CustomWarning.Conditional.GT, 5, 2);
                colour.type = CustomWarning.WarningType.Coloring; colour.color = "Red";
                var speak = Make("Sats", CustomWarning.Conditional.GT, 6, 2);
                speak.type = CustomWarning.WarningType.SpeakAndText; speak.Text = "sats {value}";
                WarningEngine.warnings.Add(colour); WarningEngine.warnings.Add(speak);
            }
            esw.Restart();
            WarningEngine.Start(null);
            Thread.Sleep(5200);
            WarningEngine.Stop();
            Thread.Sleep(500);
            var e = new StringBuilder("t_ms,kind,field,value\n");
            lock (elock) foreach (var line in events) e.AppendLine(line);
            File.WriteAllText(Path.Combine(outDir, "warnings-engine.csv"), e.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            Console.WriteLine("ENGINE_EVENTS=" + events.Count);

            // E2: colouring warning with RepeatTime 0 (what the dialog sets for colouring items), 1.2 s
            lock (elock) events.Clear();
            lock (WarningEngine.warnings)
            {
                WarningEngine.warnings.Clear();
                var colour0 = Make("Value", CustomWarning.Conditional.GT, 5, 0);
                colour0.type = CustomWarning.WarningType.Coloring; colour0.color = "Red";
                WarningEngine.warnings.Add(colour0);
            }
            esw.Restart();
            WarningEngine.Start(null);
            Thread.Sleep(1200);
            WarningEngine.Stop();
            Thread.Sleep(500);
            var e2 = new StringBuilder("t_ms,kind,field,value\n");
            lock (elock) foreach (var line in events) e2.AppendLine(line);
            File.WriteAllText(Path.Combine(outDir, "warnings-engine-colour-repeat0.csv"), e2.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            Console.WriteLine("ENGINE_COLOUR0_EVENTS=" + events.Count);

            // E3: a string-typed field first in the list, then a valid numeric warning (1.2 s)
            lock (elock) events.Clear();
            lock (WarningEngine.warnings)
            {
                WarningEngine.warnings.Clear();
                var bad = Make("ModeName", CustomWarning.Conditional.GT, 0.5, 0);
                var good = Make("Sats", CustomWarning.Conditional.GT, 6, 0);
                good.type = CustomWarning.WarningType.SpeakAndText; good.Text = "sats {value}";
                WarningEngine.warnings.Add(bad); WarningEngine.warnings.Add(good);
            }
            esw.Restart();
            WarningEngine.Start(null);
            Thread.Sleep(1200);
            WarningEngine.Stop();
            Thread.Sleep(500);
            int afterBad = events.Count;
            lock (WarningEngine.warnings)
            {
                WarningEngine.warnings.Clear();
                var good2 = Make("Sats", CustomWarning.Conditional.GT, 6, 0);
                good2.type = CustomWarning.WarningType.SpeakAndText; good2.Text = "sats {value}";
                WarningEngine.warnings.Add(good2);
            }
            esw.Restart();
            WarningEngine.Start(null);
            Thread.Sleep(1200);
            WarningEngine.Stop();
            Thread.Sleep(500);
            Console.WriteLine("ENGINE_BADFIELD_FIRST_MESSAGES={0} VALID_ONLY_MESSAGES={1}", afterBad, events.Count - afterBad);
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
