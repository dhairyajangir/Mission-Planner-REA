// Drives the original Mission Planner 1.3.83 ConfigMotorTest page against a disposable ArduCopter SITL: connects MainV2.comPort over TCP,
// builds the page (data-redirected isolated copy), calls Activate(), sets the throttle percent and duration boxes, and invokes the page's own
// button handlers by reflection: but_TestAll (every motor at once), but_TestAllSeq (one after another) and but_StopAll. Each action is printed with
// a UTC wall-clock time so that an independent observer on a second MAVLink port (sitl-servo-observer.py) can be lined up with it.
// Message boxes the page raises (for example "Command was denied by the autopilot") are logged and answered Yes by a hook.
// Simulator only, never a real vehicle, props off or not. Usage: PageMotorTestProbe.exe <isolated dir> <out dir> <SITL tcp port>
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

public static class PageMotorTestProbe
{
    static List<string> boxes = new List<string>();
    static StringBuilder log = new StringBuilder();

    public static void LogBox(string text, string caption)
    {
        lock (boxes) boxes.Add(caption + " | " + (text ?? "").Replace("\r", " ").Replace("\n", " "));
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
        var call = Expression.Call(typeof(PageMotorTestProbe).GetMethod("LogBox"), ps[0], ps[1]);
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
        return Run(dir, Path.GetFullPath(args[1]), args[2]);
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string dir, string outDir, string port)
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
                    type.GetMethod("Activate", Type.EmptyTypes).Invoke(page, null);
                    Pump(500);
                    Func<string, object> field = n => { var f = type.GetField(n, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public); return f == null ? null : f.GetValue(page); };
                    var thr = (NumericUpDown)field("NUM_thr_percent");
                    var dur = (NumericUpDown)field("NUM_duration");
                    var motormaxField = type.GetField("motormax", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                    Say("PAGE motormax=" + (motormaxField == null ? "?" : Convert.ToString(motormaxField.GetValue(page))) + " thr_percent=" + thr.Value + " duration=" + dur.Value);
                    thr.Value = 10; dur.Value = 2;
                    Say("SET thr_percent=10 duration=2");
                    Func<string, int, bool> click = (name, waitMs) =>
                    {
                        var m = type.GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                        if (m == null) { Say("NO-METHOD " + name); return false; }
                        Say("ACTION-START " + name);
                        m.Invoke(page, new object[] { null, EventArgs.Empty });
                        Say("ACTION-RETURNED " + name);
                        Pump(waitMs);
                        Say("ACTION-END " + name);
                        return true;
                    };
                    Pump(4000);               // quiet period so the observer sees the idle outputs
                    click("but_TestAll", 5000);
                    Pump(3000);
                    click("but_TestAllSeq", 14000);
                    Pump(2000);
                    click("but_StopAll", 3000);
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
        if (!th.Join(180000)) status = "timeout";
        Say("STATUS " + status);
        File.WriteAllText(Path.Combine(outDir, "motor-test-page-log.txt"), log.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
        Environment.Exit(0);
        return 0;
    }
}
