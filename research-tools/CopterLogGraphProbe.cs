// Capture the original Log Browser's curve points without starting the desktop application.
using System;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

class CopterLogGraphProbe
{
    const BindingFlags InstanceField = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;

    [STAThread]
    static int Main(string[] args)
    {
        try { Run(args); return 0; }
        catch (Exception e) { Console.Error.WriteLine(e); return 1; }
    }

    static void Run(string[] args)
    {
        string release = Path.GetFullPath(args[0]);
        string input = Path.GetFullPath(args[1]);
        string output = Path.GetFullPath(args[2]);
        string scratch = Path.GetFullPath(args[3]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) => {
            string path = Path.Combine(release, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(path) ? Assembly.LoadFrom(path) : null;
        };
        var utilities = Assembly.LoadFrom(Path.Combine(release, "MissionPlanner.Utilities.dll"));
        utilities.GetType("MissionPlanner.Utilities.Settings", true)
                 .GetField("CustomUserDataDirectory").SetValue(null, scratch);
        utilities.GetType("MissionPlanner.Utilities.Tracking", true).GetField("OptOut").SetValue(null, true);
        var maps = Assembly.LoadFrom(Path.Combine(release, "GMap.NET.Core.dll"));
        var mapManager = maps.GetType("GMap.NET.GMaps", true);
        var manager = mapManager.GetProperty("Instance", BindingFlags.Public | BindingFlags.Static |
                                                        BindingFlags.FlattenHierarchy).GetValue(null, null);
        var mode = mapManager.GetField("Mode");
        mode.SetValue(manager, Enum.Parse(mode.FieldType, "CacheOnly"));
        var exe = Assembly.LoadFrom(Path.Combine(release, "MissionPlanner.exe"));
        var browserType = exe.GetType("MissionPlanner.Log.LogBrowse", true);
        using (var browser = (Form)Activator.CreateInstance(browserType))
        using (var buffer = (IDisposable)Activator.CreateInstance(browserType.GetField("logdata", InstanceField).FieldType, input)) {
            var df = buffer.GetType().GetProperty("dflog").GetValue(buffer, null);
            browserType.GetField("logdata", InstanceField).SetValue(browser, buffer);
            browserType.GetField("dflog", InstanceField).SetValue(browser, df);
            var handle = browser.Handle; // Control.Invoke needs an owning STA handle; keep form hidden.
            var modifier = Activator.CreateInstance(browserType.GetNestedType("DataModifer", BindingFlags.NonPublic));
            var method = browserType.GetMethod("GraphItem_GetList", InstanceField);
            var graph = browserType.GetField("zg1", InstanceField).GetValue(browser);
            var clock = (CheckBox)browserType.GetField("chk_time", InstanceField).GetValue(browser);
            string[] headers = {"x_time","x_line"};
            using (var writer = new StreamWriter(output)) {
                writer.WriteLine("axis,index,x,y");
                for (int run = 0; run < 2; run++) {
                    clock.Checked = run == 0;
                    method.Invoke(browser, new object[] {"Alt", "GPS", df, modifier, true, "0", ""});
                    dynamic pane = graph.GetType().GetProperty("GraphPane").GetValue(graph, null);
                    if (pane.CurveList.Count != 1) throw new Exception("Expected exactly one curve");
                    dynamic curve = pane.CurveList[0];
                    Console.WriteLine(headers[run] + " " + curve.Label.Text + " points=" + curve.NPts);
                    for (int i = 0; i < curve.NPts; i++) {
                        dynamic point = curve.Points[i];
                        writer.WriteLine(String.Format(CultureInfo.InvariantCulture, "{0},{1},{2:R},{3:R}",
                                                       headers[run], i, (double)point.X, (double)point.Y));
                    }
                }
            }
        }
    }
}
