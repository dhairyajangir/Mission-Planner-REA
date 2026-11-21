using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;

public static class CopterBatteryRemainingProbe
{
    private static MAVLink.mavlink_battery_status_t Battery(byte id, sbyte remaining)
    {
        return new MAVLink.mavlink_battery_status_t {
            id = id, battery_remaining = remaining,
            voltages = Enumerable.Repeat(ushort.MaxValue, 10).ToArray(),
            voltages_ext = new ushort[4], current_consumed = -1, energy_consumed = -1,
            current_battery = -1, temperature = short.MaxValue
        };
    }

    public static void Main(string[] args)
    {
        System.Threading.Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        var settings = Assembly.LoadFrom("MissionPlanner.Utilities.dll").GetType("MissionPlanner.Utilities.Settings", true);
        settings.GetField("CustomUserDataDirectory").SetValue(null, Path.GetFullPath("profile"));
        Directory.CreateDirectory(Path.Combine("profile", "Mission Planner"));
        var library = Assembly.LoadFrom("MissionPlanner.ArduPilot.dll");
        dynamic port = Activator.CreateInstance(library.GetType("MissionPlanner.MAVLinkInterface", true));
        dynamic mav = port.MAVlist[1, 1];
        dynamic state = mav.cs;
        var stateType = (Type)state.GetType();
        var firmware = stateType.GetField("firmware");
        firmware.SetValue(state, Enum.Parse(firmware.FieldType, "ArduCopter2"));
        var receive = stateType.GetMethod("Parent_OnPacketReceived", BindingFlags.NonPublic | BindingFlags.Instance);
        var pack = new MAVLink.MavlinkParse();
        if (port.BaseStream != null && port.BaseStream.IsOpen)
            throw new InvalidOperationException("Expected closed interface");
        using (var output = new StreamWriter(args[0]))
        {
            output.WriteLine("step,primary_percent,secondary_percent");
            Action<string, int, int> check = (step, first, second) => {
                int observedFirst = state.battery_remaining, observedSecond = state.battery_remaining2;
                output.WriteLine("{0},{1},{2}", step, observedFirst, observedSecond);
                if (observedFirst != first || observedSecond != second)
                    throw new InvalidDataException(step + ": " + observedFirst + "," + observedSecond);
            };
            Action<MAVLink.MAVLINK_MSG_ID, object, byte> deliver = (kind, sample, system) => {
                byte[] data = pack.GenerateMAVLinkPacket20(kind, sample, false, system, 1);
                receive.Invoke(state, new object[] { port, new MAVLink.MAVLinkMessage(data) });
            };
            Action<byte, sbyte> battery = (id, remaining) =>
                deliver(MAVLink.MAVLINK_MSG_ID.BATTERY_STATUS, Battery(id, remaining), 1);
            Action<sbyte> systemStatus = remaining => deliver(MAVLink.MAVLINK_MSG_ID.SYS_STATUS,
                new MAVLink.mavlink_sys_status_t { battery_remaining = remaining, current_battery = -1 }, 1);
            check("initial", 0, 0);
            battery(0, 78); check("primary-valid", 78, 0);
            battery(1, 61); check("secondary-valid", 78, 61);
            deliver(MAVLink.MAVLINK_MSG_ID.ATTITUDE, new MAVLink.mavlink_attitude_t(), 1);
            check("other-telemetry", 78, 61);
            battery(1, -1); check("secondary-unknown", 78, -1);
            battery(0, -1); check("primary-unknown", 0, -1);
            systemStatus(54); check("system-valid", 54, -1);
            deliver(MAVLink.MAVLINK_MSG_ID.BATTERY_STATUS, Battery(0, 34), 2);
            check("other-system", 54, -1);
            systemStatus(-1); check("system-unknown", 0, -1);
            battery(0, 22); check("primary-recovery", 22, -1);
            battery(1, 35); check("secondary-recovery", 22, 35);
            battery(0, 0); check("primary-empty", 0, 35);
            battery(1, 0); check("secondary-empty", 0, 0);
        }
    }
}
