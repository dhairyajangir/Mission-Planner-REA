// Seeds marked synthetic z3 tiles only into the redirected test-copy cache.
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using GMap.NET;
using GMap.NET.MapProviders;
using MissionPlanner.Maps;

class SeedSyntheticMapTiles
{
    static int Main()
    {
        try
        {
            var implementation = new MyImageCache();
            PureImageCache cache = implementation;
            int provider = GMapProviders.OpenStreetMap.DbId;
            for (int x = 0; x < 8; x++)
                for (int y = 0; y < 8; y++)
                    if (cache.CheckImageFromCache(provider, new GPoint(x, y), 3))
                        throw new InvalidOperationException("Refusing to overwrite an existing tile at " + x + "," + y);
            int count = 0;
            for (int x = 0; x < 8; x++)
            for (int y = 0; y < 8; y++)
            {
                byte[] png;
                using (var bitmap = new Bitmap(256, 256))
                using (var graphics = Graphics.FromImage(bitmap))
                using (var memory = new MemoryStream())
                using (var font = new Font(FontFamily.GenericSansSerif, 16))
                {
                    graphics.Clear((x + y) % 2 == 0 ? Color.DarkSlateBlue : Color.DarkOliveGreen);
                    graphics.DrawString("SYNTHETIC TILE\nz3 " + x + "," + y, font, Brushes.White, 15, 20);
                    bitmap.Save(memory, ImageFormat.Png);
                    png = memory.ToArray();
                }
                if (!cache.PutImageToCache(png, provider, new GPoint(x, y), 3))
                    throw new IOException("Tile write failed at " + x + "," + y);
                count++;
            }
            Console.WriteLine("SEEDED=" + count);
            Console.WriteLine("PROVIDER=" + provider);
            Console.WriteLine("CACHE_PATH=" + implementation.CacheLocation);
            return count == 64 ? 0 : 2;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            return 1;
        }
    }
}
