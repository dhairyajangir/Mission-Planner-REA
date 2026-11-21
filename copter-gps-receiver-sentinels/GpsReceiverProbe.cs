using System;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Threading;

public static class GpsReceiverProbe
{
    public static void Main()
    {
        Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        var utilities = Assembly.LoadFrom("MissionPlanner.Utilities.dll");
        string profile = Path.GetFullPath("fixture-profile");
        Directory.CreateDirectory(Path.Combine(profile, "Mission Planner"));
        utilities.GetType("MissionPlanner.Utilities.Settings", true)
            .GetField("CustomUserDataDirectory").SetValue(null, profile);
        var core = Assembly.LoadFrom("MissionPlanner.ArduPilot.dll");
        dynamic link = Activator.CreateInstance(core.GetType("MissionPlanner.MAVLinkInterface", true));
        dynamic state = link.MAVlist[1, 1].cs;
        Type stateType = state.GetType();
        var firmware = stateType.GetField("firmware");
        firmware.SetValue(state, Enum.Parse(firmware.FieldType, "ArduCopter2"));
        var receive = stateType.GetMethod("Parent_OnPacketReceived", BindingFlags.NonPublic | BindingFlags.Instance);
        var parser = new MAVLink.MavlinkParse();
        Action<MAVLink.MAVLINK_MSG_ID, object> deliver = (id, body) =>
        {
            if (link.BaseStream != null && link.BaseStream.IsOpen) throw new InvalidOperationException("Open interface");
            var bytes = parser.GenerateMAVLinkPacket20(id, body, false, 1, 1);
            receive.Invoke(state, new object[] { link, new MAVLink.MAVLinkMessage(bytes) });
        };
        Action<string, byte, byte, ushort> observe = (label, fix, count, dilution) =>
        {
            deliver(MAVLink.MAVLINK_MSG_ID.GPS_RAW_INT, new MAVLink.mavlink_gps_raw_int_t {
                fix_type = fix, satellites_visible = count, eph = dilution
            });
            deliver(MAVLink.MAVLINK_MSG_ID.GPS2_RAW, new MAVLink.mavlink_gps2_raw_t {
                fix_type = fix, satellites_visible = count, eph = dilution
            });
            Console.WriteLine("GPS,{0},{1},{2},{3:F2},{4},{5},{6:F2},{7}", label, state.gpsstatus,
                state.satcount, state.gpshdop, state.gpsstatus2, state.satcount2, state.gpshdop2, state.satcountB);
        };
        observe("valid", 3, 10, 85);
        observe("unknown", 1, byte.MaxValue, ushort.MaxValue);
        observe("valid-zero", 1, 0, 0);
        observe("unknown-after-zero", 1, byte.MaxValue, ushort.MaxValue);
        observe("recovery", 3, 8, 95);
    }
}
