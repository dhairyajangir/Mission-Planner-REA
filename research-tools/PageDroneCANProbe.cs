// Bounded disconnected reflection probe. Cancel SLCAN warning before any serial open.
// Usage: PageDroneCANProbe.exe <data-redirected isolated dir> <new evidence dir>
using System;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Linq.Expressions;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows.Forms;

public static class PageDroneCANProbe
{
    static string output;
    static int failures, boxes;
    static readonly object gate = new object();
    static readonly BindingFlags fields = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    static void Say(string text) {
        string line = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture) + " " + text;
        lock (gate) { Console.WriteLine(line); File.AppendAllText(Path.Combine(output, "probe-log.txt"), line + "\n", new UTF8Encoding(false)); }
    }
    static void Check(string name, bool pass) { Say((pass ? "PASS " : "FAIL ") + name); if (!pass) failures++; }
    public static void Box(string text, string caption) { boxes++; Say("MESSAGEBOX answer=Cancel caption=" + caption + " text=" + text.Replace("\r", " ").Replace("\n", " ")); }
    static object Field(object obj, string name) { return obj.GetType().GetField(name, fields).GetValue(obj); }
    static void Call(object obj, string name, params object[] args) {
        var method = obj.GetType().GetMethod(name, fields);
        Say("CALL " + name + " token=0x" + method.MetadataToken.ToString("X8"));
        method.Invoke(obj, args);
    }
    static void Pump() { for (int i = 0; i < 20; i++) { Application.DoEvents(); Thread.Sleep(10); } }
    static void Capture(Control page, string name) {
        using (var bmp = new Bitmap(page.Width, page.Height)) { page.DrawToBitmap(bmp, page.ClientRectangle); bmp.Save(Path.Combine(output, name + ".png")); }
    }
    static string Cell(string text) { return "\"" + (text ?? "").Replace("\"", "\"\"") + "\""; }
    static void Controls(Control control, StringBuilder csv, string parent) {
        csv.AppendLine(string.Join(",", new[] { Cell(parent + "/" + control.Name), Cell(control.GetType().FullName), Cell(control.Text), control.Enabled.ToString(), control.Visible.ToString() }));
        foreach (Control child in control.Controls) Controls(child, csv, parent + "/" + control.Name);
    }
    static string Hash(string path) { using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(path))).Replace("-", "").ToLowerInvariant(); }

    [STAThread]
    public static int Main(string[] args) {
        string isolated = Path.GetFullPath(args[0]); output = Path.GetFullPath(args[1]);
        if (Directory.Exists(output)) throw new IOException("Evidence directory already exists; choose a new run directory.");
        Directory.CreateDirectory(output);
        new Thread(() => { Thread.Sleep(45000); Say("FAIL watchdog timeout"); Environment.Exit(2); }) { IsBackground = true }.Start();
        try {
            AppDomain.CurrentDomain.AssemblyResolve += (s, e) => {
                string name = new AssemblyName(e.Name).Name;
                string path = Path.Combine(isolated, name + ".dll");
                if (!File.Exists(path)) path = Path.Combine(isolated, name + ".exe");
                return File.Exists(path) ? Assembly.LoadFrom(path) : null;
            };
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (s, e) => { failures++; Say("FAIL thread exception " + e.Exception); };
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            var asm = Assembly.LoadFrom(Path.Combine(isolated, "MissionPlanner.exe"));
            Say("ASSEMBLY " + asm.FullName + " sha256=" + Hash(asm.Location) + " mvid=" + asm.ManifestModule.ModuleVersionId);
            var utilities = Assembly.LoadFrom(Path.Combine(isolated, "MissionPlanner.Utilities.dll"));
            var evt = utilities.GetType("System.CustomMessageBox").GetEvent("ShowEvent");
            var invoke = evt.EventHandlerType.GetMethod("Invoke");
            var ps = invoke.GetParameters().Select(p => Expression.Parameter(p.ParameterType, p.Name)).ToArray();
            var body = Expression.Block(Expression.Call(typeof(PageDroneCANProbe).GetMethod("Box"), ps[0], ps[1]), Expression.Constant(Enum.Parse(invoke.ReturnType, "Cancel"), invoke.ReturnType));
            evt.AddEventHandler(null, Expression.Lambda(evt.EventHandlerType, body, ps).Compile());
            var main = asm.GetType("MissionPlanner.MainV2");
            var comField = main.GetField("comPort", BindingFlags.Public | BindingFlags.Static);
            object com = comField != null ? comField.GetValue(null) : main.GetProperty("comPort").GetValue(null, null);
            object stream = com.GetType().GetProperty("BaseStream").GetValue(com, null);
            if (stream == null) {
                var comms = Assembly.LoadFrom(Path.Combine(isolated, "MissionPlanner.Comms.dll"));
                stream = Activator.CreateInstance(comms.GetType("MissionPlanner.Comms.CommsInjection", true));
                stream.GetType().GetMethod("Close").Invoke(stream, null);
                com.GetType().GetProperty("BaseStream").SetValue(com, stream, null);
                Say("SETUP installed closed in-memory CommsInjection; no physical or network transport");
            }
            bool streamOpen = (bool)stream.GetType().GetProperty("IsOpen").GetValue(stream, null);
            Check("MAVLink stream closed before probe", !streamOpen);
            if (streamOpen) return 1;
            var type = asm.GetType("MissionPlanner.GCSViews.ConfigurationView.ConfigDroneCAN", true);
            Say("TYPE " + type.FullName + " token=0x" + type.MetadataToken.ToString("X8"));
            using (var page = (Control)Activator.CreateInstance(type))
            using (var host = new Form { ClientSize = new Size(1100, 760), ShowInTaskbar = false, StartPosition = FormStartPosition.Manual, Location = new Point(-20000, -20000) }) {
                page.Dock = DockStyle.Fill; host.Controls.Add(page); host.Show(); Pump(); Call(page, "Activate"); Pump();
                var selector = (ComboBox)Field(page, "cmb_interfacetype");
                var network = (ComboBox)Field(page, "cmb_networkinterface");
                var connect = (Button)Field(page, "but_connect");
                var timer = (System.Windows.Forms.Timer)Field(page, "timer");
                object initialCan = Field(page, "can");
                Say("INITIAL canNull=" + (initialCan == null));
                Check("Activate starts 1000 ms timer", timer.Enabled && timer.Interval == 1000);
                Check("five interface choices", selector.Items.Count == 5);
                for (int i = 0; i < selector.Items.Count; i++) {
                    selector.SelectedIndex = i; Pump();
                    string selected = selector.SelectedValue.ToString();
                    Say("SELECT " + selected + " networkVisible=" + network.Visible + " interfaceEnabled=" + selector.Enabled + " connect=" + connect.Text);
                    Check("network selector visibility " + selected, network.Visible == selected.StartsWith("MCast"));
                }
                selector.SelectedIndex = 0; Pump(); Capture(page, "activated");
                var csv = new StringBuilder("path,type,text,enabled,visible\n"); Controls(page, csv, "");
                File.WriteAllText(Path.Combine(output, "controls.csv"), csv.ToString(), new UTF8Encoding(false));
                // SLCAN branch returns at warning because hook answers Cancel. No serial open.
                Call(page, "but_connect_Click", connect, EventArgs.Empty); Pump();
                Say("AFTER-CANCEL isConnected=" + Field(page, "isConnected") + " connect=" + connect.Text + " interfaceEnabled=" + selector.Enabled + " networkEnabled=" + network.Enabled + " canNull=" + (Field(page, "can") == null));
                Check("one disconnected SLCAN warning answered Cancel", boxes == 1);
                Check("cancel preserves initial CAN object and closed MAVLink stream", Object.ReferenceEquals(initialCan, Field(page, "can")) && !(bool)stream.GetType().GetProperty("IsOpen").GetValue(stream, null));
                Check("observed post-cancel UI remains Disconnect", (bool)Field(page, "isConnected") && connect.Text == "Disconnect" && !selector.Enabled && !network.Enabled);
                Capture(page, "cancelled-slcan");
                Call(page, "but_connect_Click", connect, EventArgs.Empty); Pump();
                Check("second click restores disconnected state", !(bool)Field(page, "isConnected") && connect.Text == "Connect" && selector.Enabled && network.Enabled);
                Call(page, "Deactivate"); Pump();
                Check("Deactivate stops timer and clears transport", !timer.Enabled && Field(page, "can") == null && !(bool)Field(page, "isConnected"));
                Capture(page, "deactivated");
                host.Close();
            }
            Say("RESULT failures=" + failures + " messageBoxes=" + boxes);
            return failures == 0 ? 0 : 1;
        } catch (Exception ex) { Say("FAIL exception " + ex); return 1; }
    }
}
