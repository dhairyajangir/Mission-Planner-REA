// Writes and decodes a synthetic in-memory tile through the distributed cache.
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using GMap.NET;
using GMap.NET.MapProviders;
using GMap.NET.WindowsForms;
using MissionPlanner.Maps;

class MissionPlannerMapDecodeProbe
{
    static int Main(string[] args)
    {
        try
        {
            if (args.Length != 1 || Directory.Exists(args[0])) return 2;
            Directory.CreateDirectory(args[0]);
            var implementation = new MyImageCache { CacheLocation = args[0] + Path.DirectorySeparatorChar };
            PureImageCache cache = implementation;
            byte[] png;
            using (var bmp = new Bitmap(2, 2))
            using (var memory = new MemoryStream())
            {
                bmp.SetPixel(0, 0, Color.Red);
                bmp.Save(memory, ImageFormat.Png);
                png = memory.ToArray();
            }
            var point = new GPoint(12500, 23500);
            int provider = GMapProviders.OpenStreetMap.DbId;
            bool inserted = cache.PutImageToCache(png, provider, point, 16);
            using (var image = cache.GetImageFromCache(provider, point, 16))
            {
                var decoded = image as GMapImage;
                if (decoded == null || decoded.Img == null) throw new InvalidDataException("Image decode failed");
                var pixel = ((Bitmap)decoded.Img).GetPixel(0, 0);
                Console.WriteLine("INSERTED=" + inserted);
                Console.WriteLine("SIZE=" + decoded.Img.Width + "x" + decoded.Img.Height);
                Console.WriteLine("FIRST_PIXEL=" + pixel.R + "," + pixel.G + "," + pixel.B);
                return inserted && decoded.Img.Width == 2 && decoded.Img.Height == 2 && pixel.R == 255 && pixel.G == 0 && pixel.B == 0 ? 0 : 3;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            return 1;
        }
    }
}
