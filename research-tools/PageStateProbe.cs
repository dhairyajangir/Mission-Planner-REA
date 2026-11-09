// For each named Mission Planner 1.3.83 setup page (original MissionPlanner.exe, data-redirected isolated copy), with MainV2.comPort
// connected to a disposable ArduCopter SITL and parameters loaded: build the page, call Activate(), pump events and record whether the
// page ended up Enabled, how many of its controls are enabled, how many interactive controls (buttons, combo boxes, numeric boxes,
// check boxes, text boxes, radio buttons) it has and how many of those are enabled, plus any message boxes it raised (logged and
// answered Yes by a hook, because the full application sets CustomMessageBox.ShowEvent at start-up and this harness does not).
// Simulator only. Usage: PageStateProbe.exe <isolated dir> <out dir> <SITL tcp port> <file with one page type name per line>
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

public static class PageStateProbe
{
    static List<string> boxes = new List<string>();
    static string currentPage = "";

    public static void LogBox(string text, string caption)
    {
        lock (boxes) boxes.Add(currentPage + " | " + caption + " | " + (text ?? "").Replace("\r", " ").Replace("\n", " "));
    }

    static void InstallMessageBoxHook(Assembly utilities)
    {
        var cmb = utilities.GetType("System.CustomMessageBox");
        var evt = cmb.GetEvent("ShowEvent");
        var del = evt.EventHandlerType;
        var invoke = del.GetMethod("Invoke");
        var ps = invoke.GetParameters().Select(p => Expression.Parameter(p.ParameterType, p.Name)).ToArray();
        var log = Expression.Call(typeof(PageStateProbe).GetMethod("LogBox"), ps[0], ps[1]);
        var body = Expression.Block(log, Expression.Constant(Enum.Parse(invoke.ReturnType, "Yes"), invoke.ReturnType));
        evt.AddEventHandler(null, Expression.Lambda(del, body, ps).Compile());
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
        return Run(dir, Path.GetFullPath(args[1]), args[2], File.ReadAllLines(args[3]));
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string dir, string outDir, string port, string[] wanted)
    {
        Directory.CreateDirectory(outDir);
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (s, e) => Console.WriteLine("THREAD-EXCEPTION " + e.Exception.GetType().Name + ": " + e.Exception.Message);
        AppDomain.CurrentDomain.UnhandledException += (s, e) => Console.WriteLine("UNHANDLED " + e.ExceptionObject);
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
        Console.WriteLine("connected; parameters: " + prm.GetType().GetProperty("Count").GetValue(prm, null));

        Type[] types;
        try { types = asm.GetTypes(); } catch (ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t != null).ToArray(); }
        var csv = new StringBuilder("page,status,detail,enabled,visible,controls_total,controls_enabled,interactive_total,interactive_enabled,message_boxes\n");
        foreach (string line in wanted)
        {
            string name = line.Trim();
            if (name.Length == 0) continue;
            currentPage = name;
            string last = name.Split('.').Last();
            var cands = types.Where(t => t.Name == last && typeof(Control).IsAssignableFrom(t)).ToList();
            var type = cands.FirstOrDefault(t => (t.FullName ?? "").EndsWith(name)) ?? cands.FirstOrDefault();
            if (type == null) { csv.AppendFormat("{0},no-type,,,,,,,,\n", name); continue; }
            string status = "", detail = ""; bool enabled = false, visible = false; int total = 0, totalEn = 0, inter = 0, interEn = 0;
            int boxesBefore; lock (boxes) boxesBefore = boxes.Count;
            var th = new Thread(() =>
            {
                try
                {
                    var c = (Control)Activator.CreateInstance(type);
                    using (var form = new Form { Width = 1000, Height = 700, ShowInTaskbar = false, StartPosition = FormStartPosition.Manual, Location = new Point(-20000, -20000) })
                    {
                        c.Dock = DockStyle.Fill;
                        form.Controls.Add(c);
                        form.Show();
                        var act = type.GetMethod("Activate", Type.EmptyTypes);
                        if (act != null) act.Invoke(c, null);
                        for (int i = 0; i < 20; i++) { Application.DoEvents(); Thread.Sleep(20); }
                        enabled = c.Enabled; visible = c.Visible;
                        var all = new List<Control>();
                        Action<Control> walk = null;
                        walk = x => { all.Add(x); foreach (Control k in x.Controls) walk(k); };
                        walk(c);
                        total = all.Count; totalEn = all.Count(x => x.Enabled);
                        Func<Control, bool> isInter = x => x is ButtonBase || x is ComboBox || x is NumericUpDown || x is TextBoxBase;
                        inter = all.Count(isInter); interEn = all.Count(x => isInter(x) && x.Enabled);
                    }
                    status = "ok";
                }
                catch (Exception ex)
                {
                    var i = ex;
                    while (i.InnerException != null) i = i.InnerException;
                    status = "exception";
                    detail = (i.GetType().Name + ": " + i.Message).Replace(",", ";").Replace("\n", " ").Replace("\r", " ");
                    if (Environment.GetEnvironmentVariable("PAGESTATE_STACK") == "1")      // add the top of the stack trace so that the failing line can be found
                    {
                        var frames = (i.StackTrace ?? "").Split('\n').Select(x => x.Trim()).Where(x => x.Length > 0).Take(4);
                        detail += " AT " + string.Join(" <- ", frames).Replace(",", ";").Replace("\r", " ");
                    }
                }
            });
            th.SetApartmentState(ApartmentState.STA);
            th.IsBackground = true;
            th.Start();
            if (!th.Join(20000)) { status = "timeout"; detail = "did not finish in 20 s (thread abandoned)"; }
            int nb; lock (boxes) nb = boxes.Count - boxesBefore;
            csv.AppendFormat("{0},{1},{2},{3},{4},{5},{6},{7},{8},{9}\n", name, status, detail, enabled, visible, total, totalEn, inter, interEn, nb);
            Console.WriteLine("{0,-34} {1,-9} enabled={2,-5} interactive {3}/{4} enabled, boxes={5} {6}", name, status, enabled, interEn, inter, nb, detail);
        }
        File.WriteAllText(Path.Combine(outDir, "page-state.csv"), csv.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
        lock (boxes) File.WriteAllText(Path.Combine(outDir, "message-boxes.txt"), string.Join("\n", boxes) + "\n", new UTF8Encoding(false));
        Environment.Exit(0);
        return 0;
    }
}
