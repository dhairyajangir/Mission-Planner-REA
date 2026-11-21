using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using MissionPlanner.GeoRef;

public class Probe
{
    public static void Main(string[] args)
    {
        Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        var folder = Path.GetFullPath(args[0]);
        MissionPlanner.Utilities.Settings.CustomUserDataDirectory = Path.Combine(folder, "profile");
        var geo = new GeoRefImageBase();
        object gate = new object();
        Action<string> message = msg => { lock (gate) Console.WriteLine("APP " + msg.TrimEnd()); };
        Console.WriteLine("ASSEMBLY " + typeof(GeoRefImageBase).Assembly.GetName().Name + " " + typeof(GeoRefImageBase).Module.ModuleVersionId);
        Console.WriteLine("INITIAL_CACHE " + geo.filedatecache.Count);
        var result = geo.doworkGPSOFFSET(Path.Combine(folder, "survey.tlog"), folder, 0f, "GPS", false, message);
        foreach (var fix in geo.vehicleLocations.OrderBy(k => k.Key))
            Console.WriteLine("FIX {0:yyyy-MM-ddTHH:mm:ss.fff} {1} {2}", fix.Value.Time, fix.Value.Lat, fix.Value.Lon);
        foreach (var file in Directory.GetFiles(folder,"*.jpg").OrderBy(f => f))
        {
            var reader = typeof(GeoRefImageBase).GetMethod("getPhotoTime", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            var taken = (DateTime)reader.Invoke(geo, new object[]{file});
            Console.WriteLine("PHOTO {0} {1:yyyy-MM-ddTHH:mm:ss.fff} {2}",Path.GetFileName(file),taken,taken.Kind);
        }
        Console.WriteLine("MATCHES " + result.Count);
        foreach (var entry in result.Values.OrderBy(r => r.Path))
        {
            Console.WriteLine("RESULT {0} {1:yyyy-MM-ddTHH:mm:ss.fff} {2:yyyy-MM-ddTHH:mm:ss.fff} {3:R} {4:R} {5:R}",
                Path.GetFileName(entry.Path),entry.ShotTimeReportedByCamera,entry.Time,entry.Lat,entry.Lon,entry.AltAMSL);
            geo.WriteCoordinatesToImage(entry.Path, entry.Lat, entry.Lon, entry.AltAMSL, folder, message);
        }
    }
}
