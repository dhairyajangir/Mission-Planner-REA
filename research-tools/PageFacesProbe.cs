// Headless construction and rendering of Mission Planner 1.3.83 setup pages from the original MissionPlanner.exe,
// loaded from the data-redirected isolated copy. Each page type is created on its own STA thread (20 s limit), laid out in
// an unshown form and drawn to a PNG. No vehicle, link or user profile is involved; pages that reference the network
// are skipped by the caller's list. Constructing a page is not the same as the page working: most pages need a connected
// vehicle and were never connected here.
// Usage: PageFacesProbe.exe <isolated dir> <out dir> <file with one page type name per line>
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

public static class PageFacesProbe
{
    static string Q(string s) { return "\"" + (s ?? "").Replace("\"", "'").Replace("\r", " ").Replace("\n", " ") + "\""; }

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
        return Run(dir, Path.GetFullPath(args[1]), File.ReadAllLines(args[2]), args.Length > 3 ? args[3] : null);
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string dir, string outDir, string[] wanted, string port)
    {
        Directory.CreateDirectory(outDir);
        Directory.CreateDirectory(Path.Combine(outDir, "png"));
        // Timer or event handlers inside pages can throw when no vehicle is connected. Log them instead of showing the
        // standard "Unhandled exception" dialog, which would block the harness and appear on the user's desktop.
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (s, e) => Console.WriteLine("THREAD-EXCEPTION " + e.Exception.GetType().Name + ": " + e.Exception.Message + " @ " + (e.Exception.StackTrace ?? "").Split('\n').FirstOrDefault());
        AppDomain.CurrentDomain.UnhandledException += (s, e) => Console.WriteLine("UNHANDLED " + e.ExceptionObject);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var asm = Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.exe"));
        Type[] types;
        try { types = asm.GetTypes(); } catch (ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t != null).ToArray(); }
        // Optional fourth argument: TCP port of a disposable SITL. MainV2.comPort is connected to it (parameters loaded) and each
        // page's Activate() is called before it is drawn.
        if (port != null)
        {
            string connectNote;
            try
            {
                var main = asm.GetType("MissionPlanner.MainV2");
                var comMember = (MemberInfo)main.GetField("comPort", BindingFlags.Public | BindingFlags.Static) ?? main.GetProperty("comPort", BindingFlags.Public | BindingFlags.Static);
                object com = comMember is FieldInfo ? ((FieldInfo)comMember).GetValue(null) : ((PropertyInfo)comMember).GetValue(null, null);
                var commsAsm = Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.Comms.dll"));
                object tcp = Activator.CreateInstance(commsAsm.GetType("MissionPlanner.Comms.TcpSerial"));
                tcp.GetType().GetProperty("Host").SetValue(tcp, "127.0.0.1", null);
                tcp.GetType().GetProperty("Port").SetValue(tcp, port, null);
                com.GetType().GetProperty("BaseStream").SetValue(com, tcp, null);
                var open = com.GetType().GetMethods().First(m => m.Name == "Open" && m.GetParameters().Length == 3 && m.GetParameters().All(p => p.ParameterType == typeof(bool)));
                open.Invoke(com, new object[] { false, false, false });   // connect only; parameters are fetched explicitly below
                object bs = com.GetType().GetProperty("BaseStream").GetValue(com, null);
                Console.WriteLine("stream open after Open: " + bs.GetType().GetProperty("IsOpen").GetValue(bs, null));
                var getList = com.GetType().GetMethods().FirstOrDefault(m => m.Name == "getParamList" && m.GetParameters().Length == 2 && m.GetParameters().All(p => p.ParameterType == typeof(byte)));
                if (getList != null) getList.Invoke(com, new object[] { (byte)1, (byte)1 });
                object mav = com.GetType().GetProperty("MAV").GetValue(com, null);
                object prm = mav.GetType().GetProperty("param").GetValue(mav, null);
                connectNote = "connected to SITL tcp " + port + "; parameters loaded: " + prm.GetType().GetProperty("Count").GetValue(prm, null);
            }
            catch (Exception ex)
            {
                var i = ex;
                while (i.InnerException != null) i = i.InnerException;
                connectNote = "connect failed: " + i.GetType().Name + ": " + i.Message;
            }
            Console.WriteLine("CONNECT: " + connectNote);
            File.WriteAllText(Path.Combine(outDir, "connect.txt"), connectNote + "\n");
        }
        var csv = new StringBuilder("page,type,status,detail,controls,texts,png,width,height\n");
        var texts = new StringBuilder();
        foreach (string line in wanted)
        {
            string name = line.Trim();
            if (name.Length == 0) continue;
            string last = name.Split('.').Last();
            var cands = types.Where(t => t.Name == last && typeof(Control).IsAssignableFrom(t)).ToList();
            var type = cands.FirstOrDefault(t => (t.FullName ?? "").EndsWith(name)) ?? cands.FirstOrDefault();
            if (type == null) { csv.AppendFormat("{0},,no-type,{1},,,,,\n", name, Q("no Control type with that name in MissionPlanner.exe")); continue; }
            string status = "", detail = ""; int controls = 0, ntexts = 0, w = 0, h = 0; string png = "";
            var th = new Thread(() =>
            {
                try
                {
                    var c = (Control)Activator.CreateInstance(type);
                    if (port != null)
                    {
                        try { var act = type.GetMethod("Activate", Type.EmptyTypes); if (act != null) act.Invoke(c, null); }
                        catch (Exception) { }
                    }
                    using (var form = new Form { Width = 1000, Height = 700, ShowInTaskbar = false, StartPosition = FormStartPosition.Manual, Location = new Point(-20000, -20000) })
                    {
                        c.Dock = DockStyle.Fill;
                        form.Controls.Add(c);
                        form.Show();   // shown far off-screen so that children are visible and paint
                        for (int i = 0; i < 15; i++) { Application.DoEvents(); Thread.Sleep(20); }
                        form.PerformLayout();
                        var all = new List<Control>();
                        Action<Control> walk = null;
                        walk = x => { all.Add(x); foreach (Control k in x.Controls) walk(k); };
                        walk(c);
                        controls = all.Count;
                        var ts = all.Where(x => (x is Label || x is ButtonBase || x is GroupBox || x is TabPage) && !string.IsNullOrWhiteSpace(x.Text))
                                    .Select(x => x.Text.Trim()).Distinct().ToList();
                        ntexts = ts.Count;
                        lock (texts) texts.AppendFormat("## {0}\n{1}\n\n", name, string.Join("\n", ts.Take(80)));
                        using (var bmp = new Bitmap(form.ClientSize.Width, form.ClientSize.Height))
                        {
                            c.DrawToBitmap(bmp, new Rectangle(0, 0, bmp.Width, bmp.Height));
                            png = Path.Combine("png", name + ".png");
                            bmp.Save(Path.Combine(outDir, png), ImageFormat.Png);
                            w = bmp.Width; h = bmp.Height;
                        }
                    }
                    status = "ok";
                }
                catch (Exception ex)
                {
                    var inner = ex;
                    while (inner.InnerException != null) inner = inner.InnerException;
                    status = "exception";
                    detail = inner.GetType().Name + ": " + inner.Message + " @ " + (inner.StackTrace ?? "").Split('\n').FirstOrDefault();
                }
            });
            th.SetApartmentState(ApartmentState.STA);
            th.IsBackground = true;
            th.Start();
            if (!th.Join(20000)) { status = "timeout"; detail = "constructor or layout did not finish in 20 s (thread abandoned)"; }
            csv.AppendFormat("{0},{1},{2},{3},{4},{5},{6},{7},{8}\n", name, type.FullName, status, Q(detail), controls, ntexts, png.Replace('\\', '/'), w, h);
            Console.WriteLine("{0,-34} {1} {2}", name, status, detail.Length > 100 ? detail.Substring(0, 100) : detail);
        }
        File.WriteAllText(Path.Combine(outDir, "faces-index.csv"), csv.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
        File.WriteAllText(Path.Combine(outDir, "faces-texts.md"), texts.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
        Environment.Exit(0);
        return 0;
    }
}
