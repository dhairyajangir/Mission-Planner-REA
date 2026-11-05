// Exercises only library properties and their event; no vehicle or transport.
using System;
using MissionPlanner;

public static class VehicleSelectionEventProbe
{
    public static int Main()
    {
        var port = new MAVLinkInterface();
        port.sysidcurrent = 1;
        port.compidcurrent = 100;
        int events = 0;
        port.MavChanged += (sender, args) => {
            events++;
            Console.WriteLine("EVENT=" + port.sysidcurrent + ":" + port.compidcurrent);
            // Mirror the main-window subscriber's access to the currently selected state.
            var state = port.MAV;
            Console.WriteLine("STATE=" + state.sysid + ":" + state.compid);
        };
        port.sysidcurrent = 2;
        port.compidcurrent = 1;
        Console.WriteLine("FINAL=" + port.sysidcurrent + ":" + port.compidcurrent + " EVENTS=" + events);
        Console.WriteLine("INTERMEDIATE_HIDDEN=" + port.MAVlist.Contains(2, 100, true) +
                          " INTERMEDIATE_VISIBLE=" + port.MAVlist.Contains(2, 100, false));
        port.MAVlist.Clear();
        Console.WriteLine("AFTER_CLEAR_HIDDEN=" + port.MAVlist.Contains(2, 100, true) +
                          " AFTER_CLEAR_VISIBLE=" + port.MAVlist.Contains(2, 100, false));
        port.logplaybackfile = null;
        Console.WriteLine("AFTER_PLAYBACK_SET_HIDDEN=" + port.MAVlist.Contains(2, 100, true) +
                          " AFTER_PLAYBACK_SET_VISIBLE=" + port.MAVlist.Contains(2, 100, false));
        return events == 2 && port.sysidcurrent == 2 && port.compidcurrent == 1 ? 0 : 1;
    }
}
