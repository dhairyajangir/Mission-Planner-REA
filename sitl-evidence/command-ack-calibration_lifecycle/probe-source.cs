// Invokes the calibration control handler directly, without rendering a screen.
// Connect only to a disposable local simulator.
using System;
using System.Reflection;
using System.Text;
using System.Windows.Forms;
using MissionPlanner;
using MissionPlanner.Comms;
public static class AccelCalibrationControlLifecycleProbe
{
    static int CountControlSubscriptions(MAVLinkInterface port, object control) {
        var list = (System.Collections.IEnumerable)typeof(MAVLinkInterface).GetField("Subscriptions", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(port);
        int count = 0;
        foreach (object item in list) {
            var function = (Delegate)item.GetType().GetField("Item2").GetValue(item);
            if (Object.ReferenceEquals(function.Target, control)) count++;
        }
        return count;
    }
    [STAThread]
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        Control control = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            Assembly main = Assembly.LoadFrom("MissionPlanner.exe");
            Type mainType = main.GetType("MissionPlanner.MainV2", true);
            Type viewType = main.GetType("MissionPlanner.GCSViews.ConfigurationView.ConfigAccelerometerCalibration", true);
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            mainType.GetProperty("comPort", BindingFlags.Public | BindingFlags.Static).SetValue(null, port, null);
            port.Open(false, false, false);
            System.Threading.Thread.Sleep(6000);
            bool arm = port.doARM(true, true);
            Console.WriteLine("ARM_COMMAND_RETURN=" + arm);
            if (!arm) throw new Exception("arm failed");
            bool armed = false;
            var deadline = DateTime.UtcNow.AddSeconds(8);
            while (DateTime.UtcNow < deadline) {
                var p = port.readPacket();
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT && p.sysid == 1 && p.compid == 1 && (p.ToStructure<MAVLink.mavlink_heartbeat_t>().base_mode & 128) != 0) { armed = true; break; }
            }
            if (!armed) throw new Exception("no armed heartbeat");
            Console.WriteLine("ARMED_HEARTBEAT=True");
            control = (Control)Activator.CreateInstance(viewType);
            IntPtr handle = control.Handle;
            viewType.GetMethod("Activate").Invoke(control, null);
            FieldInfo activeField = viewType.GetField("_incalibrate", BindingFlags.NonPublic | BindingFlags.Instance);
            FieldInfo buttonField = viewType.GetField("BUT_calib_accell", BindingFlags.NonPublic | BindingFlags.Instance);
            FieldInfo labelField = viewType.GetField("lbl_Accel_user", BindingFlags.NonPublic | BindingFlags.Instance);
            Control button = (Control)buttonField.GetValue(control);
            Control label = (Control)labelField.GetValue(control);
            Console.WriteLine("BEFORE_ACTIVE=" + activeField.GetValue(control) + " BUTTON_ENABLED=" + button.Enabled + " BUTTON_TEXT=" + button.Text);
            viewType.GetMethod("BUT_calib_accell_Click", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(control, new object[] { null, EventArgs.Empty });
            Console.WriteLine("AFTER_CLICK_ACTIVE=" + activeField.GetValue(control) + " BUTTON_ENABLED=" + button.Enabled + " BUTTON_TEXT=" + button.Text);
            bool sawNotice = false, sawFailedAck = false;
            deadline = DateTime.UtcNow.AddSeconds(8);
            while (DateTime.UtcNow < deadline && (!sawNotice || !sawFailedAck)) {
                Application.DoEvents();
                var p = port.readPacket();
                if (p.sysid != 1 || p.compid != 1) continue;
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.COMMAND_ACK) {
                    var ack = p.ToStructure<MAVLink.mavlink_command_ack_t>();
                    if (ack.command == 241 && ack.result == 4) sawFailedAck = true;
                }
                if (p.msgid == (uint)MAVLink.MAVLINK_MSG_ID.STATUSTEXT) {
                    string status = Encoding.ASCII.GetString(p.ToStructure<MAVLink.mavlink_statustext_t>().text).TrimEnd('\0');
                    if (status.Contains("Disarm to allow calibration")) sawNotice = true;
                }
            }
            Application.DoEvents();
            Console.WriteLine("SAW_FAILED_ACK=" + sawFailedAck + " SAW_NOTICE=" + sawNotice);
            Console.WriteLine("AFTER_REJECTION_ACTIVE=" + activeField.GetValue(control) + " BUTTON_ENABLED=" + button.Enabled + " BUTTON_TEXT=" + button.Text + " LABEL=" + label.Text);
            Console.WriteLine("SUBSCRIPTIONS_BEFORE_DEACTIVATE=" + CountControlSubscriptions(port, control));
            viewType.GetMethod("Deactivate").Invoke(control, null);
            Console.WriteLine("AFTER_DEACTIVATE_ACTIVE=" + activeField.GetValue(control) + " BUTTON_TEXT=" + button.Text + " SUBSCRIPTIONS=" + CountControlSubscriptions(port, control));
            viewType.GetMethod("Activate").Invoke(control, null);
            Console.WriteLine("AFTER_REACTIVATE_ACTIVE=" + activeField.GetValue(control) + " BUTTON_TEXT=" + button.Text + " SUBSCRIPTIONS=" + CountControlSubscriptions(port, control));
            viewType.GetMethod("BUT_calib_accell_Click", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(control, new object[] { null, EventArgs.Empty });
            Console.WriteLine("AFTER_RESTART_ACTIVE=" + activeField.GetValue(control) + " BUTTON_TEXT=" + button.Text + " SUBSCRIPTIONS=" + CountControlSubscriptions(port, control));
            bool sawPositionAck = false;
            deadline = DateTime.UtcNow.AddSeconds(6);
            while (DateTime.UtcNow < deadline && !sawPositionAck) {
                Application.DoEvents();
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.COMMAND_ACK || p.sysid != 1 || p.compid != 1) continue;
                var ack = p.ToStructure<MAVLink.mavlink_command_ack_t>();
                if (ack.command == (ushort)MAVLink.MAV_CMD.PREFLIGHT_CALIBRATION) { Console.WriteLine("RESTART_ACK_RESULT=" + ack.result); sawPositionAck = true; }
            }
            if (!sawPositionAck) throw new Exception("no position ACK");
            bool disarm = port.doARM(false, true);
            Console.WriteLine("DISARM_RETURN=" + disarm);
            if (!sawNotice || !sawFailedAck || !disarm) throw new Exception("incomplete evidence");
            return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (control != null) control.Dispose(); if (port != null) port.Close(); }
    }
}
