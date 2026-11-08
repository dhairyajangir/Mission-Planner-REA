// Uses a real Mission Planner 1.3.83 setup page against a disposable ArduCopter SITL: connects MainV2.comPort over TCP, builds the
// ConfigFlightModes page from the original MissionPlanner.exe (data-redirected isolated copy), calls Activate(), changes the six
// flight-mode drop-downs and the Simple / Super-Simple check boxes, invokes the page's own Save click handler (private method, by
// reflection) and reads the parameters back from the vehicle with MAVLinkInterface.GetParam(name), then restores the original
// values the same way. The page is shown off-screen; no window is operated by hand. Simulator only, never a real vehicle.
// A message box raised by the page (it shows one if a parameter write fails) would block, so each step has a 60 s limit.
// Usage: PageActionProbe.exe <isolated dir> <out dir> <SITL tcp port>
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

public static class PageActionProbe
{
    static StringBuilder csv = new StringBuilder("step,item,before,requested,read_back_from_vehicle,result\n");
    static object com;

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

    static float Get(string name)
    {
        var m = com.GetType().GetMethod("GetParam", new Type[] { typeof(string) });
        return (float)m.Invoke(com, new object[] { name });
    }

    static object Field(object o, string name)
    {
        var f = o.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        return f == null ? null : f.GetValue(o);
    }

    static void Add(string step, string item, object before, object requested, object read, string result)
    {
        csv.AppendFormat("{0},{1},{2},{3},{4},{5}\n", step, item, before, requested, read, result);
        Console.WriteLine("{0,-10} {1,-14} before={2} requested={3} read_back={4} {5}", step, item, before, requested, read, result);
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string dir, string outDir, string port)
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
        com = comMember is FieldInfo ? ((FieldInfo)comMember).GetValue(null) : ((PropertyInfo)comMember).GetValue(null, null);
        var commsAsm = Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.Comms.dll"));
        object tcp = Activator.CreateInstance(commsAsm.GetType("MissionPlanner.Comms.TcpSerial"));
        tcp.GetType().GetProperty("Host").SetValue(tcp, "127.0.0.1", null);
        tcp.GetType().GetProperty("Port").SetValue(tcp, port, null);
        com.GetType().GetProperty("BaseStream").SetValue(com, tcp, null);
        var open = com.GetType().GetMethods().First(m => m.Name == "Open" && m.GetParameters().Length == 3 && m.GetParameters().All(p => p.ParameterType == typeof(bool)));
        object openResult = open.Invoke(com, new object[] { false, false, false });
        object bs = com.GetType().GetProperty("BaseStream").GetValue(com, null);
        Console.WriteLine("Open returned: " + openResult + "; stream open: " + bs.GetType().GetProperty("IsOpen").GetValue(bs, null));
        var getList = com.GetType().GetMethods().FirstOrDefault(m => m.Name == "getParamList" && m.GetParameters().Length == 2 && m.GetParameters().All(p => p.ParameterType == typeof(byte)));
        if (getList != null) getList.Invoke(com, new object[] { (byte)1, (byte)1 });
        object mav = com.GetType().GetProperty("MAV").GetValue(com, null);
        object prm = mav.GetType().GetProperty("param").GetValue(mav, null);
        Console.WriteLine("connected; parameters: " + prm.GetType().GetProperty("Count").GetValue(prm, null));

        var type = asm.GetTypes().First(t => t.Name == "ConfigFlightModes" && typeof(Control).IsAssignableFrom(t));
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
                    for (int i = 0; i < 15; i++) { Application.DoEvents(); Thread.Sleep(20); }

                    var combos = Enumerable.Range(1, 6).Select(i => (ComboBox)Field(page, "CMB_fmode" + i)).ToArray();
                    var simple = Enumerable.Range(1, 6).Select(i => (CheckBox)Field(page, "CB_simple" + i)).ToArray();
                    var supersimple = Enumerable.Range(1, 6).Select(i => (CheckBox)Field(page, "chk_ss" + i)).ToArray();
                    var save = type.GetMethod("BUT_SaveModes_Click", BindingFlags.Instance | BindingFlags.NonPublic);
                    var saveBtn = (Control)Field(page, "BUT_SaveModes");

                    var original = combos.Select(c => Convert.ToInt32(c.SelectedValue)).ToArray();
                    for (int i = 0; i < 6; i++) Add("page-shows", "FLTMODE" + (i + 1), Get("FLTMODE" + (i + 1)), "", original[i], original[i] == (int)Get("FLTMODE" + (i + 1)) ? "page matches vehicle" : "MISMATCH");

                    // requested modes: AUTO, GUIDED, RTL, LAND, POSHOLD, BRAKE
                    int[] want = { 3, 4, 6, 9, 16, 17 };
                    for (int i = 0; i < 6; i++) combos[i].SelectedValue = want[i];
                    simple[0].Checked = true;          // SIMPLE bit for flight mode 1
                    supersimple[1].Checked = true;     // SUPER_SIMPLE bit for flight mode 2
                    save.Invoke(page, new object[] { null, EventArgs.Empty });
                    Application.DoEvents();
                    Add("save", "button text", "", "", saveBtn.Text, "");
                    for (int i = 0; i < 6; i++)
                    {
                        float rb = Get("FLTMODE" + (i + 1));
                        Add("save", "FLTMODE" + (i + 1), original[i], want[i], rb, (int)rb == want[i] ? "applied" : "NOT applied");
                    }
                    float s1 = Get("SIMPLE"), s2 = Get("SUPER_SIMPLE");
                    Add("save", "SIMPLE", "", 1, s1, (int)s1 == 1 ? "applied" : "NOT applied");
                    Add("save", "SUPER_SIMPLE", "", 2, s2, (int)s2 == 2 ? "applied" : "NOT applied");

                    // restore
                    for (int i = 0; i < 6; i++) combos[i].SelectedValue = original[i];
                    simple[0].Checked = false;
                    supersimple[1].Checked = false;
                    save.Invoke(page, new object[] { null, EventArgs.Empty });
                    Application.DoEvents();
                    for (int i = 0; i < 6; i++)
                    {
                        float rb = Get("FLTMODE" + (i + 1));
                        Add("restore", "FLTMODE" + (i + 1), want[i], original[i], rb, (int)rb == original[i] ? "restored" : "NOT restored");
                    }
                    s1 = Get("SIMPLE"); s2 = Get("SUPER_SIMPLE");
                    Add("restore", "SIMPLE", "", 0, s1, (int)s1 == 0 ? "restored" : "NOT restored");
                    Add("restore", "SUPER_SIMPLE", "", 0, s2, (int)s2 == 0 ? "restored" : "NOT restored");
                }
                status = "ok";
            }
            catch (Exception ex)
            {
                var i = ex;
                while (i.InnerException != null) i = i.InnerException;
                status = "exception: " + i.GetType().Name + ": " + i.Message + " @ " + (i.StackTrace ?? "").Split('\n').FirstOrDefault();
            }
        });
        th.SetApartmentState(ApartmentState.STA);
        th.IsBackground = true;
        th.Start();
        if (!th.Join(60000)) status = "timeout (60 s; a message box may have been shown)";
        Console.WriteLine("STATUS: " + status);
        File.WriteAllText(Path.Combine(outDir, "page-action-flightmodes.csv"), csv.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
        File.WriteAllText(Path.Combine(outDir, "page-action-status.txt"), status + "\n");
        Environment.Exit(0);
        return 0;
    }
}
