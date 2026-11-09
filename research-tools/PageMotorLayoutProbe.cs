// Builds the original Mission Planner 1.3.83 ConfigMotorTest page (data-redirected isolated copy) against a disposable ArduCopter SITL, calls Activate() and lists
// what the page shows without pressing any test button: the motor count it settled on, the class/type text it printed, every button (text and tag) and every
// label (text and position) in its motor group. Used to see which buttons and "Motor Number" labels the page draws for each frame. No MAVLink command is sent
// by this probe. Simulator only, never a real vehicle.
// Usage: PageMotorLayoutProbe.exe <isolated dir> <out dir> <SITL tcp port> <log name>
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Linq.Expressions;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

public static class PageMotorLayoutProbe
{
    static StringBuilder log = new StringBuilder();

    public static void LogBox(string text, string caption)
    {
        Say("MESSAGEBOX " + caption + " | " + (text ?? "").Replace("\r", " ").Replace("\n", " "));
    }

    static void Say(string s)
    {
        string line = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture) + " " + s;
        Console.WriteLine(line);
        lock (log) log.AppendLine(line);
    }

    static void InstallMessageBoxHook(Assembly utilities)
    {
        var cmb = utilities.GetType("System.CustomMessageBox");
        var evt = cmb.GetEvent("ShowEvent");
        var del = evt.EventHandlerType;
        var invoke = del.GetMethod("Invoke");
        var ps = invoke.GetParameters().Select(p => Expression.Parameter(p.ParameterType, p.Name)).ToArray();
        var call = Expression.Call(typeof(PageMotorLayoutProbe).GetMethod("LogBox"), ps[0], ps[1]);
        var body = Expression.Block(call, Expression.Constant(Enum.Parse(invoke.ReturnType, "Yes"), invoke.ReturnType));
        evt.AddEventHandler(null, Expression.Lambda(del, body, ps).Compile());
    }

    static void Pump(int ms)
    {
        var end = DateTime.UtcNow.AddMilliseconds(ms);
        while (DateTime.UtcNow < end) { Application.DoEvents(); Thread.Sleep(20); }
    }

    public static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string n = new AssemblyName(e.Name).Name;
            string p = Path.Combine(dir, n + ".dll");
            if (!File.Exists(p)) p = Path.Combine(dir, n + ".exe");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        return Run(dir, Path.GetFullPath(args[1]), args[2], args[3], new string[0]);
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string dir, string outDir, string port, string logName, string[] actions)
    {
        Directory.CreateDirectory(outDir);
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (s, e) => Say("THREAD-EXCEPTION " + e.Exception.GetType().Name + ": " + e.Exception.Message);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var asm = Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.exe"));
        var main = asm.GetType("MissionPlanner.MainV2");
        var comMember = (MemberInfo)main.GetField("comPort", BindingFlags.Public | BindingFlags.Static) ?? main.GetProperty("comPort", BindingFlags.Public | BindingFlags.Static);
        object com = comMember is FieldInfo ? ((FieldInfo)comMember).GetValue(null) : ((PropertyInfo)comMember).GetValue(null, null);
        InstallMessageBoxHook(Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.Utilities.dll")));
        var commsAsm = Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.Comms.dll"));
        object tcp = Activator.CreateInstance(commsAsm.GetType("MissionPlanner.Comms.TcpSerial"));
        tcp.GetType().GetProperty("Host").SetValue(tcp, "127.0.0.1", null);
        tcp.GetType().GetProperty("Port").SetValue(tcp, port, null);
        com.GetType().GetProperty("BaseStream").SetValue(com, tcp, null);
        var open = com.GetType().GetMethods().First(m => m.Name == "Open" && m.GetParameters().Length == 3 && m.GetParameters().All(p => p.ParameterType == typeof(bool)));
        open.Invoke(com, new object[] { false, false, false });
        var getList = com.GetType().GetMethods().FirstOrDefault(m => m.Name == "getParamList" && m.GetParameters().Length == 2 && m.GetParameters().All(p => p.ParameterType == typeof(byte)));
        if (getList != null) getList.Invoke(com, new object[] { (byte)1, (byte)1 });
        object mav = com.GetType().GetProperty("MAV").GetValue(com, null);
        object prm = mav.GetType().GetProperty("param").GetValue(mav, null);
        Say("CONNECTED parameters=" + prm.GetType().GetProperty("Count").GetValue(prm, null));
        var getParam = com.GetType().GetMethods().FirstOrDefault(m => m.Name == "GetParam" && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType == typeof(string));

        Func<string, string> vehicleValue = name =>
        {
            try { return getParam == null ? "?" : Convert.ToString(getParam.Invoke(com, new object[] { name }), CultureInfo.InvariantCulture); }
            catch (Exception ex) { var i = ex; while (i.InnerException != null) i = i.InnerException; return "error:" + i.Message; }
        };

        var type = asm.GetTypes().First(t => t.Name == "ConfigMotorTest" && typeof(Control).IsAssignableFrom(t));
        string status = "";
        var th = new Thread(() =>
        {
            try
            {
                var page = (Control)Activator.CreateInstance(type);
                using (var form = new Form { Width = 1000, Height = 700, ShowInTaskbar = false, StartPosition = FormStartPosition.Manual, Location = new Point(-20000, -20000) })
                {
                    page.Dock = DockStyle.Fill;
                    form.Controls.Add(page);
                    form.Show();
                    Say("BEFORE-ACTIVATE vehicle FRAME_CLASS=" + vehicleValue("FRAME_CLASS") + " FRAME_TYPE=" + vehicleValue("FRAME_TYPE"));
                    type.GetMethod("Activate", Type.EmptyTypes).Invoke(page, null);
                    Pump(1500);
                    var mm = type.GetField("motormax", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                    Say("PAGE enabled=" + page.Enabled + " motormax=" + (mm == null ? "?" : Convert.ToString(mm.GetValue(page))));
                    Func<string, Control> ctl = n => { var f = type.GetField(n, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public); return f == null ? null : (Control)f.GetValue(page); };
                    foreach (var n in new[] { "FrameClass", "FrameType" }) { var c = ctl(n); Say("TEXT " + n + " = " + (c == null ? "?" : c.Text)); }
                    var gb = ctl("groupBox1");
                    if (gb != null)
                    {
                        foreach (Control c in gb.Controls.Cast<Control>().OrderBy(x => x.Location.Y).ThenBy(x => x.Location.X))
                        {
                            Say((c is Button ? "BUTTON" : c is Label ? "LABEL" : c.GetType().Name.ToUpper()) + " y=" + c.Location.Y + " x=" + c.Location.X + " text=" + c.Text.Replace("\n", " ") + (c.Tag == null ? "" : " tag=" + c.Tag));
                        }
                    }
                }
                status = "ok";
            }
            catch (Exception ex)
            {
                var i = ex;
                while (i.InnerException != null) i = i.InnerException;
                status = "exception: " + i.GetType().Name + ": " + i.Message;
            }
        });
        th.SetApartmentState(ApartmentState.STA);
        th.IsBackground = true;
        th.Start();
        if (!th.Join(120000)) status = "timeout";
        Say("STATUS " + status);
        File.WriteAllText(Path.Combine(outDir, logName), log.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
        Environment.Exit(0);
        return 0;
    }
}
