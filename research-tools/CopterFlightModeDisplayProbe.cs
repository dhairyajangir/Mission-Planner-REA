using System;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

// Exercise the release page's timer callback in memory. No main window or transport is opened.
public static class CopterFlightModeDisplayProbe
{
    [STAThread]
    public static int Main(string[] args)
    {
        try { return Run(args); }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }

    static int Run(string[] args)
    {
        Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        Thread.CurrentThread.CurrentUICulture = CultureInfo.GetCultureInfo("en-US");
        var settings = Assembly.LoadFrom("MissionPlanner.Utilities.dll").GetType("MissionPlanner.Utilities.Settings", true);
        settings.GetField("CustomUserDataDirectory").SetValue(null, Path.GetFullPath("profile"));
        Directory.CreateDirectory(Path.Combine("profile", "Mission Planner"));
        var assembly = Assembly.LoadFrom("MissionPlanner.exe");
        var main = assembly.GetType("MissionPlanner.MainV2", true);
        dynamic port = main.GetProperty("comPort").GetValue(null, null);
        dynamic mav = port.MAV;
        dynamic state = mav.cs;
        var firmware = ((Type)state.GetType()).GetField("firmware");
        firmware.SetValue(state, Enum.Parse(firmware.FieldType, "ArduCopter2"));
        Func<bool> streamOpen = () => port.BaseStream != null && port.BaseStream.IsOpen;
        if (streamOpen()) throw new InvalidOperationException("Expected a disconnected interface");
        var parameter = Assembly.LoadFrom("MAVLink.dll").GetType("MAVLink+MAVLinkParam", true);
        var constructor = parameter.GetConstructors().Single(c => c.GetParameters().Length == 4 && c.GetParameters()[1].ParameterType == typeof(double));
        var real32 = Enum.Parse(constructor.GetParameters()[2].ParameterType, "REAL32");
        Action<string, int> add = (key, value) => mav.param.Add((dynamic)constructor.Invoke(new object[] { key, (double)value, real32, null }));
        var pageType = assembly.GetType("MissionPlanner.GCSViews.ConfigurationView.ConfigFlightModes", true);
        var tick = pageType.GetMethod("timer_Tick", BindingFlags.NonPublic | BindingFlags.Instance);
        var marker = Color.Lime;
        assembly.GetType("MissionPlanner.Utilities.ThemeManager", true).GetField("CurrentPPMBackground").SetValue(null, marker);
        using (var page = (Control)Activator.CreateInstance(pageType))
        using (var file = new StreamWriter(args[0], false, new System.Text.UTF8Encoding(false)))
        {
            file.WriteLine("case,fltmode_ch,mode_ch,seed_channel,seed_pwm,expected_slot,actual_slot,expected_label,actual_label");
            var slots = Enumerable.Range(1, 6).Select(i => page.Controls.Find("CMB_fmode" + i, true).Single()).ToArray();
            var label = page.Controls.Find("LBL_flightmodepwm", true).Single();
            Action<string, int?, int?, int, float, int, string> check = (name, flt, mode, channel, pwm, expected, expectedLabel) =>
            {
                mav.param.Clear();
                if (flt.HasValue) add("FLTMODE_CH", flt.Value);
                if (mode.HasValue) add("MODE_CH", mode.Value);
                Type stateType = state.GetType();
                for (int i = 5; i <= 16; i++)
                    stateType.GetProperty("ch" + i + "in").SetValue(state, i == channel ? pwm : 1000f, null);
                tick.Invoke(page, new object[] { null, EventArgs.Empty });
                var actual = string.Join("|", Enumerable.Range(0, 6).Where(i => slots[i].BackColor.ToArgb() == marker.ToArgb()).Select(i => (i + 1).ToString()));
                file.WriteLine(string.Join(",", name, flt, mode, channel, pwm, expected, actual, expectedLabel, label.Text));
                file.Flush();
                if (actual != expected.ToString() || label.Text != expectedLabel || streamOpen())
                    throw new InvalidOperationException("Unexpected result for " + name + ": slot=" + actual + ", label=" + label.Text);
            };
            check("absent-initial", null, null, 5, 1800, 1, "0");
            int[] boundaries = { 1230, 1360, 1490, 1620, 1749 };
            for (int i = 0; i < boundaries.Length; i++)
            {
                foreach (float delta in new float[] { 0f, 0.75f, 1f })
                {
                    float pwm = boundaries[i] + delta;
                    check("threshold", 5, null, 5, pwm, delta < 1 ? i + 1 : i + 2, "5: " + pwm);
                }
            }
            for (int i = 5; i <= 16; i++)
                check("channel", i, null, i, 1810 + i, 6, i + ": " + (1810 + i));
            check("mode-only", null, 7, 7, 1400, 3, "7: 1400");
            check("flt-first", 9, 7, 9, 1580, 4, "9: 1580");
            check("absent-after-valid", null, null, 9, 1580, 1, "9: 1580");
            foreach (int i in new int[] { 0, 4, 17 })
                check("unsupported", i, 7, 7, 1800, 1, i + ": 0");
        }
        return 0;
    }
}
