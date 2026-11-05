// Exercises the distributed GMap cache with a synthetic local-only payload.
using System;
using System.IO;
using System.Text;
using GMap.NET;
using GMap.NET.MapProviders;
using MissionPlanner.Maps;

class MissionPlannerMapCacheProbe
{
    static int Main(string[] args)
    {
        try
        {
            if (args.Length != 1 || Directory.Exists(args[0])) return 2;
            Directory.CreateDirectory(args[0]);
            var implementation = new MyImageCache { CacheLocation = args[0] };
            PureImageCache cache = implementation;
            var tile = Encoding.ASCII.GetBytes("offline-cache-fixture-v1");
            var position = new GPoint(12345, 23456);
            var providerObject = GMapProviders.OpenStreetMap;
            int provider = providerObject.DbId;
            bool inserted = cache.PutImageToCache(tile, provider, position, 16);
            bool found = cache.CheckImageFromCache(provider, position, 16);
            bool missing = cache.CheckImageFromCache(provider, new GPoint(12346, 23456), 16);
            Console.WriteLine("PROVIDER_ID=" + provider);
            Console.WriteLine("INSERTED=" + inserted);
            Console.WriteLine("FOUND=" + found);
            Console.WriteLine("MISSING_FOUND=" + missing);
            var file = Path.Combine(implementation.CacheLocation, providerObject.Name, "16", "23456", "12345.jpg");
            var firstBytes = File.ReadAllBytes(file);
            bool overwrite = cache.PutImageToCache(Encoding.ASCII.GetBytes("x"), provider, position, 16);
            var secondBytes = File.ReadAllBytes(file);
            Console.WriteLine("FIRST_LENGTH=" + firstBytes.Length);
            Console.WriteLine("FIRST_MATCH=" + (Encoding.ASCII.GetString(firstBytes) == "offline-cache-fixture-v1"));
            Console.WriteLine("OVERWRITE_OK=" + overwrite);
            Console.WriteLine("SECOND_LENGTH=" + secondBytes.Length);
            Console.WriteLine("SECOND_CONTENT=" + Encoding.ASCII.GetString(secondBytes));
            Console.WriteLine("CACHE_DIR=" + implementation.CacheLocation);
            return inserted && found && !missing ? 0 : 3;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            return 1;
        }
    }
}
