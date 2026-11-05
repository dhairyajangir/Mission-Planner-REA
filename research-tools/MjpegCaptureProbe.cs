using System;
using System.Drawing;
using System.Threading;
using MissionPlanner.Utilities;

public static class MjpegCaptureProbe
{
    static int count;
    static bool cleared;
    static bool clearBeforeFrame;
    static readonly object gate = new object();
    static readonly ManualResetEvent done = new ManualResetEvent(false);
    public static int Main()
    {
        bool expectReconnect = Environment.GetEnvironmentVariable("MJPEG_EXPECT_RECONNECT") == "1";
        log4net.Config.BasicConfigurator.Configure();
        CaptureMJPEG.onNewImage += (sender, frame) =>
        {
            lock (gate)
            {
                if (frame == null)
                {
                    cleared = true;
                    if (count == 0) clearBeforeFrame = true;
                    Console.WriteLine("CLEAR_EVENT=True");
                    if (!expectReconnect || count >= 3) done.Set();
                    return;
                }
                Color pixel = frame.GetPixel(frame.Width / 2, frame.Height / 2);
                count++;
                Console.WriteLine("FRAME=" + count + " SIZE=" + frame.Width + "x" + frame.Height +
                                  " RGB=" + pixel.R + "," + pixel.G + "," + pixel.B);
                if (count >= 3) CaptureMJPEG.Stop();
            }
        };
        CaptureMJPEG.URL = "http://127.0.0.1:6690/video";
        CaptureMJPEG.runAsync();
        bool signal = done.WaitOne(TimeSpan.FromSeconds(25));
        CaptureMJPEG.Stop();
        lock (gate)
        {
            Console.WriteLine("FRAMES=" + count);
            Console.WriteLine("STOP_CLEAR=" + cleared);
            Console.WriteLine("CLEAR_BEFORE_FRAME=" + clearBeforeFrame);
            return signal && cleared && count >= 3 && (!expectReconnect || clearBeforeFrame) ? 0 : 1;
        }
    }
}
