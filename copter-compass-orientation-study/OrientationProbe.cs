using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;

class OrientationProbe
{
    const int Count = 122;
    const double Field = 500;
    static readonly string[] Cases = { "full_sphere", "level_ring", "ring_plus_poles" };

    static List<Tuple<float, float, float>> Samples(string name)
    {
        var data = new List<Tuple<float, float, float>>();
        for (int i = 0; i < Count; i++)
        {
            double z = 0, angle = 2 * Math.PI * i / Count;
            if (name == "full_sphere")
            {
                z = 1 - 2.0 * (i + 0.5) / Count;
                angle = i * Math.PI * (3 - Math.Sqrt(5));
            }
            else if (name == "ring_plus_poles" && i >= Count - 2)
                z = i == Count - 2 ? -1 : 1;
            double rad = Field * Math.Sqrt(1 - z * z);
            data.Add(Tuple.Create((float)(120 + rad * Math.Cos(angle)),
                                  (float)(-80 + rad * Math.Sin(angle)), (float)(150 + Field * z)));
        }
        return data;
    }

    static void Main(string[] args)
    {
        System.Threading.Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        string release = Path.GetFullPath(args[0]);
        Assembly program = Assembly.LoadFrom(Path.Combine(release, "MissionPlanner.exe"));
        var fit = program.GetType("MissionPlanner.MagCalib", true).GetMethod("LeastSq",
            new[] { typeof(List<Tuple<float, float, float>>), typeof(bool) });
        foreach (string name in Cases)
        {
            var samples = Samples(name);
            var result = (double[])fit.Invoke(null, new object[] { samples, false });
            Console.WriteLine("FIT|{0}|{1}|{2:R}|{3:R}|{4:R}|{5:R}", name, samples.Count,
                              result[0], result[1], result[2], result[3]);
        }
        foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
        {
            if (assembly.IsDynamic || String.IsNullOrEmpty(assembly.Location)) continue;
            if (String.Equals(Path.GetDirectoryName(assembly.Location), release, StringComparison.OrdinalIgnoreCase))
                Console.WriteLine("RELEASE|" + Path.GetFileName(assembly.Location));
        }
        Console.WriteLine("METHOD|" + fit.MetadataToken.ToString("x8") + "|" + fit.Module.ModuleVersionId);
    }
}
