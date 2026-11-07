// Library-level probe of the original Mission Planner 1.3.83 JoystickBase. No vehicle, no hardware, no network.
// A fake device drives the real pickchannel/Expo mapping and the real mainloop thread; output is a golden-vector CSV
// plus lifecycle observations. It does NOT run MainV2's sender thread (that code stays source-only).
// Usage: JoystickMappingProbe.exe <dir with original MissionPlanner DLLs> <golden-csv-out>
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Joystick;
using MissionPlanner.Utilities;

sealed class FakeState : IMyJoystickState
{
    public int AZ { get; set; } public int AY { get; set; } public int AX { get; set; }
    public int ARz { get; set; } public int ARy { get; set; } public int ARx { get; set; }
    public int FRx { get; set; } public int FRy { get; set; } public int FRz { get; set; }
    public int FX { get; set; } public int FY { get; set; } public int FZ { get; set; }
    public int Rx { get; set; } public int Ry { get; set; } public int Rz { get; set; }
    public int VRx { get; set; } public int VRy { get; set; } public int VRz { get; set; }
    public int VX { get; set; } public int VY { get; set; } public int VZ { get; set; }
    public int X { get; set; } public int Y { get; set; } public int Z { get; set; }
    public int[] GetSlider() { return new int[] { 0, 0 }; }
    public int[] GetPointOfView() { return new int[] { -1 }; }
    public bool[] GetButtons() { return new bool[128]; }
}

sealed class FakeJoystick : JoystickBase
{
    public readonly FakeState S = new FakeState();
    public volatile bool Valid = true;
    public FakeJoystick(Func<MAVLinkInterface> f) : base(f) { }
    public override bool AcquireJoystick(string n) { return true; }
    public override int getNumberPOV() { return 0; }
    public override void UnAcquireJoyStick() { }
    public override int getNumButtons() { return 0; }
    public override bool IsJoystickValid() { return Valid; }
    public override IMyJoystickState GetCurrentState() { return S; }
    public short Pick(int chan, joystickaxis axis, bool rev, int expo) { state = S; return pickchannel(chan, axis, rev, expo); }
}

public static class JoystickMappingProbe
{
    static void SetRc(MAVLinkInterface mav, int chan, bool min, bool max, bool trim, int lo, int hi, int mid)
    {
        if (min) mav.MAV.param["RC" + chan + "_MIN"] = new MAVLink.MAVLinkParam("RC" + chan + "_MIN", lo, MAVLink.MAV_PARAM_TYPE.REAL32);
        if (max) mav.MAV.param["RC" + chan + "_MAX"] = new MAVLink.MAVLinkParam("RC" + chan + "_MAX", hi, MAVLink.MAV_PARAM_TYPE.REAL32);
        if (trim) mav.MAV.param["RC" + chan + "_TRIM"] = new MAVLink.MAVLinkParam("RC" + chan + "_TRIM", mid, MAVLink.MAV_PARAM_TYPE.REAL32);
    }

    public static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string p = Path.Combine(dir, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        return Run(args[1]);
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string csvPath)
    {
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            string data = Settings.GetUserDataDirectory();
            string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            Console.WriteLine("USER_DATA_DIR=" + data);
            if (data.StartsWith(appdata, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("refusing to run: data directory is not redirected away from the real profile");

            var csv = new StringBuilder("profile,chan,axis,raw,reverse,expo,result\n");
            int[] raws = { 0, 1, 8192, 16384, 24576, 32767, 32768, 40960, 49152, 57344, 65535 };
            int[] expos = { -30, 0, 20, 50 };
            int[] chans = { 1, 3, 5 };
            string[] profiles = { "default", "rc-custom", "rc-partial", "manual-control" };
            int rows = 0;
            foreach (var profile in profiles)
            {
                var mav = new MAVLinkInterface();
                var joy = new FakeJoystick(() => mav);
                if (profile == "rc-custom") foreach (int c in chans) SetRc(mav, c, true, true, true, 1100, 1900, 1480);
                if (profile == "rc-partial") foreach (int c in chans) SetRc(mav, c, true, false, false, 1100, 1900, 1480);
                joy.manual_control = profile == "manual-control";
                foreach (int c in chans)
                    foreach (bool rev in new[] { false, true })
                        foreach (int expo in expos)
                            foreach (int raw in raws)
                            {
                                joy.S.X = raw;
                                short r = joy.Pick(c, joystickaxis.X, rev, expo);
                                csv.AppendFormat("{0},{1},X,{2},{3},{4},{5}\n", profile, c, raw, rev ? 1 : 0, expo, r);
                                rows++;
                            }
                foreach (int c in chans)
                    foreach (var ax in new[] { joystickaxis.Pass, joystickaxis.UINT16_MAX, joystickaxis.None })
                    {
                        short r = joy.Pick(c, ax, false, 0);
                        csv.AppendFormat("{0},{1},{2},0,0,0,{3}\n", profile, c, ax, r);
                        rows++;
                    }
            }
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(csvPath)));
            File.WriteAllText(csvPath, csv.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            Console.WriteLine("GOLDEN_ROWS=" + rows);

            // Expo() directly: documented range input -500..500, min/max/mid as passed.
            foreach (double v in new double[] { -500, -250, -100, 0, 100, 250, 500 })
                Console.WriteLine("EXPO input={0} expo=20 min=1000 max=2000 mid=1500 -> {1}", v, JoystickBase.Expo(v, 20, 1000, 2000, 1500));

            // Lifecycle: real mainloop thread, closed link (no packets are sent; DoJoystickButtonFunction is gated on IsOpen).
            var lm = new MAVLinkInterface();
            var lj = new FakeJoystick(() => lm);
            lj.setChannel(1, joystickaxis.X, false, 0);
            lj.setChannel(3, joystickaxis.Y, false, 0);
            lj.S.X = 65535; lj.S.Y = 0;
            bool started = lj.start("fake");
            Thread.Sleep(300);
            Console.WriteLine("LIFE_STARTED={0} ENABLED={1} CH1={2} CH3={3} CH2={4}", started, lj.enabled, lm.MAV.cs.rcoverridech1, lm.MAV.cs.rcoverridech3, lm.MAV.cs.rcoverridech2);
            lj.S.X = 0;
            Thread.Sleep(300);
            Console.WriteLine("LIFE_AXIS_MOVED CH1={0}", lm.MAV.cs.rcoverridech1);
            lj.Valid = false;        // simulate unplug: IsJoystickValid() turns false
            Thread.Sleep(200);
            lj.S.X = 65535;          // move the stick after the device is gone
            Thread.Sleep(300);
            Console.WriteLine("LIFE_AFTER_UNPLUG ENABLED={0} CH1={1} CH3={2}", lj.enabled, lm.MAV.cs.rcoverridech1, lm.MAV.cs.rcoverridech3);
            lj.clearRCOverride();
            Console.WriteLine("LIFE_AFTER_CLEAR ENABLED={0} CH1={1} CH3={2}", lj.enabled, lm.MAV.cs.rcoverridech1, lm.MAV.cs.rcoverridech3);
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
