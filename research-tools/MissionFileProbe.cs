// Exercise local mission file conversion through distributed Mission Planner libraries.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using MissionPlanner.Utilities;

public static class MissionFileProbe
{
    static void Dump(string label, List<Locationwp> points)
    {
        Console.WriteLine(label + " COUNT=" + points.Count);
        for (int i = 0; i < points.Count; i++)
        {
            Locationwp p = points[i];
            Console.WriteLine(label + " ITEM=" + i + " ID=" + p.id + " FRAME=" + p.frame +
                " P1=" + p.p1.ToString("R", CultureInfo.InvariantCulture) +
                " LAT=" + p.lat.ToString("R", CultureInfo.InvariantCulture) +
                " LON=" + p.lng.ToString("R", CultureInfo.InvariantCulture) +
                " ALT=" + p.alt.ToString("R", CultureInfo.InvariantCulture));
        }
    }
    public static int Main(string[] args)
    {
        try
        {
            string folder = args[0];
            Directory.CreateDirectory(folder);
            string header = "QGC WPL 110\n";
            string home = "0\t1\t0\t16\t0\t0\t0\t0\t-35.363261\t149.165230\t584\t1\n";
            string point = "1\t0\t3\t16\t2\t0\t0\t0\t-35.362500\t149.166000\t25\t1\n";
            File.WriteAllText(Path.Combine(folder, "normal.waypoints"), header + home + point);
            File.WriteAllText(Path.Combine(folder, "no-home.waypoints"), header + point);
            File.WriteAllText(Path.Combine(folder, "flag-variant.waypoints"), header + home + point.Replace("1\t0\t3", "1\t1\t3").Replace("\t25\t1", "\t25\t0"));
            var normal = WaypointFile.ReadWaypointFile(Path.Combine(folder, "normal.waypoints"));
            Dump("TEXT", normal);
            Dump("NO_HOME", WaypointFile.ReadWaypointFile(Path.Combine(folder, "no-home.waypoints")));
            Dump("FLAG_VARIANT", WaypointFile.ReadWaypointFile(Path.Combine(folder, "flag-variant.waypoints")));
            var generated = MissionFile.ConvertFromLocationwps(normal, 3);
            string path = Path.Combine(folder, "generated.mission");
            MissionFile.WriteFile(path, generated);
            Console.WriteLine("GENERATED ITEM_TYPE=" + (generated.mission.items[0].type ?? "<null>") +
                              " FRAME=" + generated.mission.items[0].frame +
                              " AUTOCONTINUE=" + generated.mission.items[0].autoContinue);
            var reread = MissionFile.ReadFile(path);
            Dump("JSON_READBACK", MissionFile.ConvertToLocationwps(reread));
            reread.mission.items[0].type = "SimpleItem";
            Dump("JSON_SIMPLE_CONTROL", MissionFile.ConvertToLocationwps(reread));
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
