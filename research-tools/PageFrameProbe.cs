// Drives the original Mission Planner 1.3.83 ConfigFrameClassType page against a disposable ArduCopter SITL. Connects MainV2.comPort over TCP,
// builds the page (data-redirected isolated copy), calls Activate(), prints the state the page shows (which class and type radio buttons are
// checked, which type radios are enabled, whether the type group is enabled) next to the vehicle's FRAME_CLASS and FRAME_TYPE read back from the
// vehicle, then runs the actions given on the command line. An action sets a radio button's Checked property, which runs the page's own
// CheckedChanged handler and so its own FRAME_CLASS and FRAME_TYPE writes; after each action the state and the vehicle's values are printed again.
// Message boxes are logged and answered Yes. Simulator only, never a real vehicle.
// Usage: PageFrameProbe.exe <isolated dir> <out dir> <SITL tcp port> <log name> [action ...]    action = radioButtonHexa | radioButton_X | ...
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

public static class PageFrameProbe
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
        var call = Expression.Call(typeof(PageFrameProbe).GetMethod("LogBox"), ps[0], ps[1]);
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
        return Run(dir, Path.GetFullPath(args[1]), args[2], args[3], args.Skip(4).ToArray());
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

        var type = asm.GetTypes().First(t => t.Name == "ConfigFrameClassType" && typeof(Control).IsAssignableFrom(t));
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
                    Func<string, object> field = n => { var f = type.GetField(n, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public); return f == null ? null : f.GetValue(page); };
                    var radios = type.GetFields(BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)
                        .Where(f => typeof(RadioButton).IsAssignableFrom(f.FieldType)).Select(f => new { f.Name, R = (RadioButton)f.GetValue(page) }).Where(x => x.R != null).ToList();
                    Action<string> dump = tag =>
                    {
                        var cls = radios.Where(x => x.Name.StartsWith("radioButton") && !x.Name.StartsWith("radioButton_")).ToList();
                        var typ = radios.Where(x => x.Name.StartsWith("radioButton_")).ToList();
                        var g2 = field("groupBox2") as Control;
                        Say("STATE " + tag + " class_checked=[" + string.Join(",", cls.Where(x => x.R.Checked).Select(x => x.Name)) + "] type_checked=[" +
                            string.Join(",", typ.Where(x => x.R.Checked).Select(x => x.Name)) + "] type_enabled=[" + string.Join(",", typ.Where(x => x.R.Enabled).Select(x => x.Name)) +
                            "] type_group_enabled=" + (g2 == null ? "?" : g2.Enabled.ToString()) + " page_enabled=" + page.Enabled +
                            " vehicle FRAME_CLASS=" + vehicleValue("FRAME_CLASS") + " FRAME_TYPE=" + vehicleValue("FRAME_TYPE"));
                    };
                    Say("BEFORE-ACTIVATE vehicle FRAME_CLASS=" + vehicleValue("FRAME_CLASS") + " FRAME_TYPE=" + vehicleValue("FRAME_TYPE"));
                    type.GetMethod("Activate", Type.EmptyTypes).Invoke(page, null);
                    Pump(1500);
                    dump("after-activate");
                    foreach (var a in actions)
                    {
                        var r = radios.FirstOrDefault(x => x.Name == a);
                        if (r == null) { Say("NO-RADIO " + a); continue; }
                        Say("ACTION " + a + " (set Checked=true)");
                        r.R.Checked = true;
                        Pump(1500);
                        dump("after-" + a);
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
