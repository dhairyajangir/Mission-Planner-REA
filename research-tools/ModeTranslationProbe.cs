// Original translateMode using fixed tracker modes; no transport or physical vehicle.
using System;
using MissionPlanner;
using MissionPlanner.ArduPilot;
public static class ModeTranslationProbe
{
    public static int Main()
    {
        try
        {
            var port = new MAVLinkInterface();
            port.MAVlist[1, 1].cs.firmware = Firmwares.ArduTracker;
            foreach (string name in new[] { "SCAN", "scan", "not-a-mode", "", (string)null })
            {
                var mode = new MAVLink.mavlink_set_mode_t();
                bool result = port.translateMode(1, 1, name, ref mode);
                string label = name == null ? "<null>" : name == "" ? "<empty>" : name;
                Console.WriteLine("NAME=" + label + " RESULT=" + result + " TARGET=" + mode.target_system +
                                  " BASE=" + mode.base_mode + " CUSTOM=" + mode.custom_mode);
            }
            var stale = new MAVLink.mavlink_set_mode_t { base_mode = 1, custom_mode = 2 };
            bool staleResult = port.translateMode(1, 1, "not-a-mode", ref stale);
            Console.WriteLine("STALE_INPUT RESULT=" + staleResult + " TARGET=" + stale.target_system +
                              " BASE=" + stale.base_mode + " CUSTOM=" + stale.custom_mode);
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
