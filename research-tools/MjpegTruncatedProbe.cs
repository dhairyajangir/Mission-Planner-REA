using System;
using System.Reflection;
using System.Diagnostics;
using System.Threading;
using MissionPlanner.Utilities;

public static class MjpegTruncatedProbe
{
    public static int Main()
    {
        log4net.Config.BasicConfigurator.Configure();
        int frames = 0, clears = 0;
        CaptureMJPEG.onNewImage += (sender, frame) =>
        {
            if (frame == null) Interlocked.Increment(ref clears);
            else Interlocked.Increment(ref frames);
        };
        CaptureMJPEG.URL = "http://127.0.0.1:6690/video";
        CaptureMJPEG.runAsync();
        Thread.Sleep(2500);
        CaptureMJPEG.Stop();
        var cpuBefore = Process.GetCurrentProcess().TotalProcessorTime;
        Thread.Sleep(1500);
        var cpuUsed = (Process.GetCurrentProcess().TotalProcessorTime - cpuBefore).TotalMilliseconds;
        var field = typeof(CaptureMJPEG).GetField("asyncthread", BindingFlags.Static | BindingFlags.NonPublic);
        var worker = (Thread)field.GetValue(null);
        Console.WriteLine("FRAMES=" + frames);
        Console.WriteLine("CLEAR_EVENTS=" + clears);
        Console.WriteLine("WORKER_ALIVE_AFTER_STOP=" + (worker != null && worker.IsAlive));
        Console.WriteLine("CPU_MS_DURING_STOP_WAIT=" + cpuUsed.ToString(System.Globalization.CultureInfo.InvariantCulture));
        var restart = new Thread(() => CaptureMJPEG.runAsync());
        restart.IsBackground = true;
        restart.Start();
        bool restartReturned = restart.Join(1000);
        Console.WriteLine("RESTART_RETURNED_WITHIN_1S=" + restartReturned);
        return worker != null && worker.IsAlive && frames == 0 ? 0 : 1;
    }
}
