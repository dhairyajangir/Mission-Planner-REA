// Synthetic files only; calls the distributed Mission Planner waypoint reader.
using System;
using System.Globalization;
using System.IO;
using MissionPlanner.Utilities;
class WaypointImportEdgesProbe {
    static void Run(string dir, string name, string contents) {
        string path = Path.Combine(dir, name + ".waypoints");
        File.WriteAllText(path, contents);
        var items = WaypointFile.ReadWaypointFile(path);
        Console.WriteLine(name + " COUNT=" + items.Count);
        for (int i=0; i<items.Count; i++) {
            var p = items[i];
            Console.WriteLine(string.Format(CultureInfo.InvariantCulture, "{0} ITEM={1} ID={2} FRAME={3} LAT={4:R} LON={5:R} ALT={6:R}", name, i, p.id, p.frame, p.lat, p.lng, p.alt));
        }
    }
    static int Main(string[] args) {
        try {
            Directory.CreateDirectory(args[0]);
            string hdr = "QGC WPL 110\n";
            string home = "0\t1\t0\t16\t0\t0\t0\t0\t-35.363261\t149.165230\t584\t1\n";
            string wp1 = "1\t0\t3\t16\t0\t0\t0\t0\t-35.363100\t149.165100\t21\t1\n";
            string wp2 = "2\t0\t3\t16\t0\t0\t0\t0\t-35.363200\t149.165200\t22\t1\n";
            Run(args[0], "short_row", hdr + home + "1\t0\t3\t16\t0\t0\t0\t0\t-35.363100\n" + wp2);
            Run(args[0], "duplicate_sequence", hdr + home + wp1 + wp1.Replace("21\t1", "23\t1"));
            Run(args[0], "nonfinite", hdr + home + wp1.Replace("-35.363100", "NaN"));
            Run(args[0], "loose_header", "prefix QGC WPL unexpected\n" + home + wp1);
            Run(args[0], "gap_sequence", hdr + home + wp2);
            return 0;
        } catch (Exception ex) { Console.WriteLine("UNHANDLED=" + ex); return 1; }
    }
}
