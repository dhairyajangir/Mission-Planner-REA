// Inspect selected synthetic JSON plan cases through the distributed utility DLL.
using System;
using System.Globalization;
using System.IO;
using MissionPlanner.Utilities;

public static class MissionPlanProbe
{
    public static int Main(string[] args)
    {
        foreach (string name in new[] { "valid.plan", "complex-missing.plan", "short-params.plan" })
        {
            Console.WriteLine("CASE=" + name);
            try
            {
                var plan = MissionFile.ReadFile(Path.Combine(args[0], name));
                var points = MissionFile.ConvertToLocationwps(plan);
                Console.WriteLine("COUNT=" + points.Count);
                for (int i = 0; i < points.Count; i++)
                {
                    var p = points[i];
                    Console.WriteLine("ITEM=" + i + " ID=" + p.id + " FRAME=" + p.frame +
                        " P1=" + p.p1.ToString("R", CultureInfo.InvariantCulture) +
                        " P2=" + p.p2.ToString("R", CultureInfo.InvariantCulture) +
                        " LAT=" + p.lat.ToString("R", CultureInfo.InvariantCulture) +
                        " LON=" + p.lng.ToString("R", CultureInfo.InvariantCulture) +
                        " ALT=" + p.alt.ToString("R", CultureInfo.InvariantCulture));
                }
            }
            catch (Exception ex) { Console.WriteLine("EXCEPTION=" + ex.GetType().FullName); }
        }
        return 0;
    }
}
