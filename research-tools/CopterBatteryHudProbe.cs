using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Threading;

public static class CopterBatteryHudProbe
{
    [STAThread]
    public static void Main(string[] args)
    {
        Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        Thread.CurrentThread.CurrentUICulture = CultureInfo.GetCultureInfo("en-US");
        var dll = Assembly.LoadFrom("MissionPlanner.Controls.dll");
        var type = dll.GetType("MissionPlanner.Controls.HUD", true);
        var paint = type.GetMethod("doPaint", BindingFlags.Instance | BindingFlags.NonPublic);
        var core = Assembly.LoadFrom("MissionPlanner.ArduPilot.dll");
        dynamic state = Activator.CreateInstance(core.GetType("MissionPlanner.CurrentState", true));
        var cases = new[] {
            new { Name = "dual-valid", First = 78, Second = 61, Voltage = 11.4f, Icons = false },
            new { Name = "primary-unknown", First = -1, Second = 61, Voltage = 11.4f, Icons = false },
            new { Name = "primary-empty", First = 0, Second = 61, Voltage = 11.4f, Icons = false },
            new { Name = "secondary-unknown", First = 78, Second = -1, Voltage = 11.4f, Icons = false },
            new { Name = "secondary-empty", First = 78, Second = 0, Voltage = 11.4f, Icons = false },
            new { Name = "secondary-no-volts-unknown", First = 78, Second = -1, Voltage = 0f, Icons = false },
            new { Name = "secondary-no-volts-empty", First = 78, Second = 0, Voltage = 0f, Icons = false },
            new { Name = "icons-secondary-unknown", First = 78, Second = -1, Voltage = 11.4f, Icons = true },
            new { Name = "icons-secondary-empty", First = 78, Second = 0, Voltage = 11.4f, Icons = true }
        };
        foreach (var sample in cases)
        {
            dynamic hud = Activator.CreateInstance(type);
            try
            {
                hud.opengl = false;
                hud.Size = new Size(800, 480);
                hud.batteryon = hud.batteryon2 = true;
                hud.displayCellVoltage = false;
                hud.displayicons = sample.Icons;
                hud.batterylevel = 12.25f;
                hud.batterylevel2 = sample.Voltage;
                hud.current = 3f;
                hud.current2 = 2f;
                state.battery_remaining = sample.First;
                state.battery_remaining2 = sample.Second;
                hud.batteryremaining = (float)state.battery_remaining;
                hud.batteryremaining2 = (float)state.battery_remaining2;
                paint.Invoke(hud, null);
                Bitmap full = hud.objBitmap;
                using (var crop = full.Clone(new Rectangle(0, 410, 310, 70), PixelFormat.Format32bppArgb))
                    crop.Save(Path.Combine(args[0], sample.Name + ".png"), ImageFormat.Png);
            }
            finally { hud.Dispose(); }
        }
    }
}
