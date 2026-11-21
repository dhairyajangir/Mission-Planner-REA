// Drive the archived GPS receive callback and record a software-rendered HUD crop.
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Threading;

public class CopterGpsFixHudProbe
{
    [STAThread]
    public static void Main(string[] args)
    {
        Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        Thread.CurrentThread.CurrentUICulture = CultureInfo.GetCultureInfo("en-US");
        var util = Assembly.LoadFrom("MissionPlanner.Utilities.dll");
        string profile = Path.GetFullPath("profile");
        Directory.CreateDirectory(Path.Combine(profile, "Mission Planner"));
        util.GetType("MissionPlanner.Utilities.Settings", true).GetField("CustomUserDataDirectory").SetValue(null, profile);
        var core = Assembly.LoadFrom("MissionPlanner.ArduPilot.dll");
        dynamic link = Activator.CreateInstance(core.GetType("MissionPlanner.MAVLinkInterface", true));
        dynamic state = link.MAVlist[1, 1].cs;
        Type st = state.GetType();
        FieldInfo firmware = st.GetField("firmware");
        firmware.SetValue(state, Enum.Parse(firmware.FieldType, "ArduCopter2"));
        var receive = st.GetMethod("Parent_OnPacketReceived", BindingFlags.Instance | BindingFlags.NonPublic);
        var pack = new MAVLink.MavlinkParse();
        Action<MAVLink.MAVLINK_MSG_ID,object> deliver = (id, body) => {
            if (link.BaseStream != null && link.BaseStream.IsOpen) throw new InvalidOperationException("Expected closed interface");
            byte[] frame = pack.GenerateMAVLinkPacket20(id, body, false, 1, 1);
            receive.Invoke(state, new object[] { link, new MAVLink.MAVLinkMessage(frame) });
        };
        Action<byte,int,int,int,byte,ushort> gps = (fix, lat, lon, altitude, sats, hdop) =>
            deliver(MAVLink.MAVLINK_MSG_ID.GPS_RAW_INT, new MAVLink.mavlink_gps_raw_int_t {
                fix_type = fix, lat = lat, lon = lon, alt = altitude, satellites_visible = sats, eph = hdop
            });
        Action<int,int,int,int> global = (lat, lon, altitude, rel) =>
            deliver(MAVLink.MAVLINK_MSG_ID.GLOBAL_POSITION_INT, new MAVLink.mavlink_global_position_int_t {
                lat = lat, lon = lon, alt = altitude, relative_alt = rel
            });
        var controls = Assembly.LoadFrom("MissionPlanner.Controls.dll");
        var hudType = controls.GetType("MissionPlanner.Controls.HUD", true);
        var paint = hudType.GetMethod("doPaint", BindingFlags.NonPublic | BindingFlags.Instance);
        string output = args[0];
        using (var writer = new StreamWriter(Path.Combine(output, "observed.csv"))) {
            writer.WriteLine("step,fix,satellites,hdop,latitude,longitude,alt_asl_m,alt_relative_m");
            Action<string,bool> capture = (stage, render) => {
                writer.WriteLine("{0},{1},{2},{3},{4:F7},{5:F7},{6:F2},{7:F2}",
                    stage, state.gpsstatus, state.satcount, state.gpshdop, state.lat, state.lng, state.altasl, state.alt);
                if (render) {
                    dynamic hud = Activator.CreateInstance(hudType);
                    try {
                        hud.Size = new Size(800,480);
                        hud.opengl = false;
                        hud.displaygps = true;
                        hud.displayicons = false;
                        hud.gpsfix = (float)state.gpsstatus;
                        hud.gpshdop = (float)state.gpshdop;
                        paint.Invoke(hud, null);
                        Bitmap full = hud.objBitmap;
                        using (var crop = full.Clone(new Rectangle(580,436,220,44), PixelFormat.Format32bppArgb))
                            crop.Save(Path.Combine(output, stage + ".png"), ImageFormat.Png);
                    } finally { hud.Dispose(); }
                }
            };
            gps(3,100000000,200000000,101000,12,85); capture("raw-3d",true);
            gps(1,100000000,200000000,101000,4,275); capture("raw-lost-last-position",true);
            gps(1,0,0,0,4,275); capture("raw-lost-zero-position",false);
            gps(3,100100000,200100000,102000,11,95); capture("raw-recovered",true);
            global(101000000,201000000,123000,12000); capture("global-position",false);
            gps(1,0,0,0,3,315); capture("global-lost",false);
            global(101100000,201100000,124000,13000); capture("global-update-while-lost",false);
            gps(3,100200000,200200000,103000,11,95); capture("global-recovered",false);
        }
    }
}
