// Synthetic parameter files through the distributed Mission Planner utility library.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using MissionPlanner.Utilities;

public static class ParamFileProbe
{
    static string F(double value) { return value.ToString("R", CultureInfo.InvariantCulture); }
    static void Dump(string label, Dictionary<string, double> values)
    {
        Console.WriteLine(label + " COUNT=" + values.Count);
        foreach (var name in new SortedSet<string>(values.Keys, StringComparer.Ordinal))
            Console.WriteLine(label + " KEY=" + name + " VALUE=" + F(values[name]));
    }
    static void TryRead(string folder, string name)
    {
        try { Dump(name, ParamFile.loadParamFile(Path.Combine(folder, name))); }
        catch (Exception ex) { Console.WriteLine(name + " EXCEPTION=" + ex.GetType().FullName + " MESSAGE=" + ex.Message); }
    }
    public static int Main(string[] args)
    {
        try
        {
            string folder = args[0];
            Directory.CreateDirectory(folder);
            File.WriteAllText(Path.Combine(folder, "normal.param"),
                "# comment\nALPHA,1.25\nDUP 1\nDUP\t2\nSYS_NUM_RESETS,42\nFORMAT_VERSION,120\nDECIMAL_COMMA,1,25\nEXP,1.5e-2\nNAN,NaN\n");
            File.WriteAllText(Path.Combine(folder, "bad-excluded.param"), "FORMAT_VERSION,not-a-number\n");
            File.WriteAllText(Path.Combine(folder, "indented-comment.param"), "  # note\n");
            File.WriteAllText(Path.Combine(folder, "bad-value.param"), "GOOD,1\nBROKEN,not-a-number\n");
            foreach (string name in new[] { "normal.param", "bad-excluded.param", "indented-comment.param", "bad-value.param" })
                TryRead(folder, name);
            var previous = CultureInfo.CurrentCulture;
            try
            {
                CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE");
                var values = new Hashtable { { "BETA", 12.5 }, { "ALPHA", -0.125 }, { "FORMAT_VERSION", 120.0 } };
                string saved = Path.Combine(folder, "saved.param");
                ParamFile.SaveParamFile(saved, values);
                Console.WriteLine("SAVED CULTURE=" + CultureInfo.CurrentCulture.Name);
                Dump("SAVED_READBACK", ParamFile.loadParamFile(saved));
            }
            finally { CultureInfo.CurrentCulture = previous; }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
