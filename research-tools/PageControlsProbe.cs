// For each named Mission Planner 1.3.83 setup page (built from the original MissionPlanner.exe in the data-redirected isolated copy):
// connect MainV2.comPort to a disposable ArduCopter SITL, call Activate(), find every parameter-bound control (MavlinkNumericUpDown,
// MavlinkCheckBox) whose parameter exists on the vehicle, change it by one step, wait for the control's own write path (the numeric
// control writes through a 300 ms timer, the check box on CheckedChanged), read the parameter back from the vehicle with
// MAVLinkInterface.GetParam(name), then put the control back and check the vehicle value was restored. Simulator only.
// MavlinkComboBox controls are moved to the next item on pages without a staged write button (the expected value is the selected key,
// or the enum value parsed from the text, matching the control's two write paths) and then put back; on staged pages they are listed only.
// A message box raised by a control would block its page thread; each page has a time limit and is then abandoned.
// Usage: PageControlsProbe.exe <isolated dir> <out dir> <SITL tcp port> <page type names, comma separated>
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

public static class PageControlsProbe
{
    static StringBuilder csv = new StringBuilder("page,control,param,kind,before,target,expected,staged_read_before_commit,read_after,applied,restored_read,restored\n");
    static object com;
    static object paramList;
    static List<string> boxes = new List<string>();
    static string currentPage = "";

    // pages with a staged write: edits are collected and written only when this private click handler runs
    static Dictionary<string, string> commitHandler = new Dictionary<string, string> { { "ConfigArducopter", "BUT_writePIDS_Click" } };

    // called by the message box hook: the full application sets CustomMessageBox.ShowEvent at start-up, this harness does not
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
        var log = Expression.Call(typeof(PageControlsProbe).GetMethod("LogBox"), ps[0], ps[1]);
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
        return Run(dir, Path.GetFullPath(args[1]), args[2], args[3].Split(',').Select(x => x.Trim()).Where(x => x.Length > 0).ToArray());
    }

    static float Get(string name)
    {
        var m = com.GetType().GetMethod("GetParam", new Type[] { typeof(string) });
        return (float)m.Invoke(com, new object[] { name });
    }

    static bool HasParam(string name)
    {
        var m = paramList.GetType().GetMethod("ContainsKey", new Type[] { typeof(string) });
        return m != null && (bool)m.Invoke(paramList, new object[] { name });
    }

    static void Pump(int ms)
    {
        var end = DateTime.UtcNow.AddMilliseconds(ms);
        while (DateTime.UtcNow < end) { Application.DoEvents(); Thread.Sleep(20); }
    }

    static bool Close(float a, double b)
    {
        return Math.Abs(a - b) <= 1e-4 * Math.Max(1.0, Math.Abs(b));
    }

    static string F(object v) { return Convert.ToString(v, CultureInfo.InvariantCulture); }

    static void Row(string page, string ctl, string param, string kind, object before, object target, object expected, object staged, object read, string applied, object rrestored, string restored)
    {
        csv.AppendFormat(CultureInfo.InvariantCulture, "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11}\n", page, ctl, param, kind, F(before), F(target), F(expected), F(staged), F(read), applied, F(rrestored), restored);
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string dir, string outDir, string port, string[] pages)
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
        InstallMessageBoxHook(Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.Utilities.dll")));
        var commsAsm = Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.Comms.dll"));
        object tcp = Activator.CreateInstance(commsAsm.GetType("MissionPlanner.Comms.TcpSerial"));
        tcp.GetType().GetProperty("Host").SetValue(tcp, "127.0.0.1", null);
        tcp.GetType().GetProperty("Port").SetValue(tcp, port, null);
        com.GetType().GetProperty("BaseStream").SetValue(com, tcp, null);
        var open = com.GetType().GetMethods().First(m => m.Name == "Open" && m.GetParameters().Length == 3 && m.GetParameters().All(p => p.ParameterType == typeof(bool)));
        open.Invoke(com, new object[] { false, false, false });
        object bs = com.GetType().GetProperty("BaseStream").GetValue(com, null);
        Console.WriteLine("stream open: " + bs.GetType().GetProperty("IsOpen").GetValue(bs, null));
        var getList = com.GetType().GetMethods().FirstOrDefault(m => m.Name == "getParamList" && m.GetParameters().Length == 2 && m.GetParameters().All(p => p.ParameterType == typeof(byte)));
        if (getList != null) getList.Invoke(com, new object[] { (byte)1, (byte)1 });
        object mav = com.GetType().GetProperty("MAV").GetValue(com, null);
        paramList = mav.GetType().GetProperty("param").GetValue(mav, null);
        Console.WriteLine("connected; parameters: " + paramList.GetType().GetProperty("Count").GetValue(paramList, null));

        var summary = new StringBuilder("page,status,detail,numeric_total,numeric_changed,numeric_applied,numeric_restored,checkbox_total,checkbox_changed,checkbox_applied,checkbox_restored,combo_listed,combo_changed,combo_applied,combo_restored\n");
        Type[] all;
        try { all = asm.GetTypes(); } catch (ReflectionTypeLoadException ex) { all = ex.Types.Where(t => t != null).ToArray(); }
        foreach (string pageName in pages)
        {
            currentPage = pageName;
            var type = all.FirstOrDefault(t => t.Name == pageName && typeof(Control).IsAssignableFrom(t));
            if (type == null) { summary.AppendFormat("{0},no-type,,,,,,,,,,\n", pageName); continue; }
            string status = "", detail = "";
            int nTot = 0, nChg = 0, nApp = 0, nRes = 0, cTot = 0, cChg = 0, cApp = 0, cRes = 0, combos = 0, combosChg = 0, combosApp = 0, combosRes = 0;
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
                        var act = type.GetMethod("Activate", Type.EmptyTypes);
                        if (act != null) act.Invoke(page, null);
                        Pump(400);
                        var ctls = new List<Control>();
                        Action<Control> walk = null;
                        walk = x => { ctls.Add(x); foreach (Control k in x.Controls) walk(k); };
                        walk(page);
                        string commitName;
                        MethodInfo commit = commitHandler.TryGetValue(pageName, out commitName) ? type.GetMethod(commitName, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public) : null;
                        var staged = new List<object[]>();   // control, param name, original, target, scale, vehicle value before
                        foreach (var c in ctls)
                        {
                            string tn = c.GetType().Name;
                            if (tn != "MavlinkNumericUpDown" && tn != "MavlinkCheckBox" && tn != "MavlinkComboBox") continue;
                            string pname = (string)c.GetType().GetProperty("ParamName").GetValue(c, null);
                            if (string.IsNullOrEmpty(pname) || !HasParam(pname)) continue;
                            if (tn == "MavlinkComboBox")
                            {
                                combos++;
                                if (commit != null) continue;     // staged pages: combo edits are collected by the page, not written (not tested)
                                var cmb = (ComboBox)c;
                                if (cmb.Items.Count < 2 || cmb.SelectedIndex < 0) continue;
                                // the control writes either the selected key (key/value source) or the parsed enum name (enum source)
                                var f2 = c.GetType().GetField("_source2", BindingFlags.Instance | BindingFlags.NonPublic);
                                var f1 = c.GetType().GetField("_source", BindingFlags.Instance | BindingFlags.NonPublic);
                                object src2 = f2 == null ? null : f2.GetValue(c), src1 = f1 == null ? null : f1.GetValue(c);
                                Func<double?> expectedNow = () =>
                                {
                                    try
                                    {
                                        if (src1 != null) return (double)(int)Enum.Parse((Type)src1, cmb.Text);
                                        if (src2 != null) return Convert.ToDouble(cmb.SelectedValue, CultureInfo.InvariantCulture);
                                    }
                                    catch { }
                                    return null;
                                };
                                if (expectedNow() == null) continue;
                                int origIdx = cmb.SelectedIndex;
                                float beforeC = Get(pname);
                                string origText = cmb.Text;
                                cmb.SelectedIndex = (origIdx + 1) % cmb.Items.Count;
                                Pump(600);
                                string targetText = cmb.Text;      // captured before the control is put back
                                double? exp = expectedNow();
                                float readC = Get(pname);
                                bool appliedC = exp.HasValue && Close(readC, exp.Value);
                                cmb.SelectedIndex = origIdx;
                                Pump(600);
                                float backC = Get(pname);
                                bool restoredC = Close(backC, beforeC);
                                combosChg++; if (appliedC) combosApp++; if (restoredC) combosRes++;
                                Row(pageName, c.Name, pname, "combo", beforeC + " (" + origText.Replace(",", ";") + ")", targetText.Replace(",", ";"), exp, "", readC, appliedC ? "applied" : "NOT applied", backC, restoredC ? "restored" : "NOT restored");
                                continue;
                            }
                            if (tn == "MavlinkNumericUpDown")
                            {
                                var n = (NumericUpDown)c;
                                nTot++;
                                float scale = 1f;
                                var sf = c.GetType().GetField("_scale", BindingFlags.Instance | BindingFlags.NonPublic);
                                if (sf != null) scale = Convert.ToSingle(sf.GetValue(c), CultureInfo.InvariantCulture);
                                decimal orig = n.Value, step = n.Increment <= 0 ? 1 : n.Increment;
                                decimal target = orig + step <= n.Maximum ? orig + step : orig - step;
                                if (target < n.Minimum || target == orig) continue;
                                float before = Get(pname);
                                if (commit != null) { staged.Add(new object[] { n, pname, orig, target, scale, before }); continue; }
                                double expected = (double)(float)target * scale;
                                n.Value = target;
                                Pump(900);
                                float read = Get(pname);
                                bool applied = Close(read, expected);
                                n.Value = orig;
                                Pump(900);
                                float back = Get(pname);
                                bool restored = Close(back, before);
                                nChg++; if (applied) nApp++; if (restored) nRes++;
                                Row(pageName, c.Name, pname, "numeric", before, target, expected, "", read, applied ? "applied" : "NOT applied", back, restored ? "restored" : "NOT restored");
                            }
                            else
                            {
                                var cb = (CheckBox)c;
                                cTot++;
                                double on = (double)c.GetType().GetProperty("OnValue").GetValue(c, null);
                                double off = (double)c.GetType().GetProperty("OffValue").GetValue(c, null);
                                float before = Get(pname);
                                bool origChecked = cb.Checked;
                                double expected = origChecked ? off : on;
                                cb.Checked = !origChecked;
                                Pump(400);
                                float read = Get(pname);
                                bool applied = Close(read, expected);
                                cb.Checked = origChecked;
                                Pump(400);
                                float back = Get(pname);
                                bool restored = Close(back, before);
                                cChg++; if (applied) cApp++; if (restored) cRes++;
                                Row(pageName, c.Name, pname, "checkbox", before, !origChecked, expected, "", read, applied ? "applied" : "NOT applied", back, restored ? "restored" : "NOT restored");
                            }
                        }
                        if (commit != null && staged.Count > 0)
                        {
                            // phase 1: edit every control; the vehicle must still hold the old values (the page only stages them)
                            foreach (var s in staged) ((NumericUpDown)s[0]).Value = (decimal)s[3];
                            Pump(900);
                            var stagedRead = staged.Select(s => Get((string)s[1])).ToList();
                            // phase 2: run the page's own write button handler
                            commit.Invoke(page, new object[] { null, EventArgs.Empty });
                            Pump(900);
                            var afterRead = staged.Select(s => Get((string)s[1])).ToList();
                            // phase 3: put every control back and write again
                            foreach (var s in staged) ((NumericUpDown)s[0]).Value = (decimal)s[2];
                            Pump(900);
                            commit.Invoke(page, new object[] { null, EventArgs.Empty });
                            Pump(900);
                            for (int i = 0; i < staged.Count; i++)
                            {
                                var s = staged[i];
                                double expected = (double)(float)(decimal)s[3] * Convert.ToDouble(s[4], CultureInfo.InvariantCulture);
                                float back = Get((string)s[1]);
                                bool applied = Close(afterRead[i], expected), restored = Close(back, (float)s[5]);
                                nChg++; if (applied) nApp++; if (restored) nRes++;
                                Row(pageName, ((Control)s[0]).Name, (string)s[1], "numeric-staged", s[5], s[3], expected, stagedRead[i], afterRead[i], applied ? "applied" : "NOT applied", back, restored ? "restored" : "NOT restored");
                            }
                        }
                    }
                    status = "ok";
                }
                catch (Exception ex)
                {
                    var i = ex;
                    while (i.InnerException != null) i = i.InnerException;
                    status = "exception";
                    detail = (i.GetType().Name + ": " + i.Message).Replace(",", ";").Replace("\n", " ");
                }
            });
            th.SetApartmentState(ApartmentState.STA);
            th.IsBackground = true;
            th.Start();
            if (!th.Join(600000)) { status = "timeout"; detail = "page thread did not finish in 600 s (a message box may be open)"; }
            summary.AppendFormat("{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14}\n", pageName, status, detail, nTot, nChg, nApp, nRes, cTot, cChg, cApp, cRes, combos, combosChg, combosApp, combosRes);
            Console.WriteLine("{0}: {1} {2} numeric changed {3}/{4} applied {5} restored {6}; checkbox changed {7}/{8} applied {9} restored {10}; combos {11} (changed {12} applied {13} restored {14})", pageName, status, detail, nChg, nTot, nApp, nRes, cChg, cTot, cApp, cRes, combos, combosChg, combosApp, combosRes);
            lock (boxes) File.WriteAllText(Path.Combine(outDir, "message-boxes.txt"), string.Join("\n", boxes) + "\n", new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(outDir, "page-controls.csv"), csv.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(outDir, "page-controls-summary.csv"), summary.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
        }
        Environment.Exit(0);
        return 0;
    }
}
