using System;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Joystick;
using MissionPlanner.Utilities;

sealed class ObservedJoystick : JoystickBase
{
    public readonly FakeState Input = new FakeState();
    public readonly ManualResetEvent SawLoss = new ManualResetEvent(false);
    public volatile bool Available = true;

    public ObservedJoystick(Func<MAVLinkInterface> link) : base(link) { }
    public override bool AcquireJoystick(string name) { return true; }
    public override void UnAcquireJoyStick() { }
    public override int getNumberPOV() { return 0; }
    public override int getNumButtons() { return 0; }
    public override IMyJoystickState GetCurrentState() { return Input; }
    public override bool IsJoystickValid()
    {
        bool valid = Available;
        if (!valid) SawLoss.Set();
        return valid;
    }
}

static class ConfirmedLifecycle
{
    public static void Run()
    {
        var link = new MAVLinkInterface();
        var joy = new ObservedJoystick(() => link);
        joy.setChannel(1, joystickaxis.X, false, 0);
        joy.setChannel(3, joystickaxis.Y, false, 0);
        joy.Input.X = 65535;
        if (!joy.start("simulated") || !SpinWait.SpinUntil(() =>
                link.MAV.cs.rcoverridech1 == 2000 && link.MAV.cs.rcoverridech3 == 1000, 10000))
            throw new InvalidOperationException("Never observed initial channel update");
        Console.WriteLine("CONFIRMED_STARTED ENABLED={0} CH1={1} CH3={2}", joy.enabled,
                          link.MAV.cs.rcoverridech1, link.MAV.cs.rcoverridech3);
        joy.Input.X = 0;
        if (!SpinWait.SpinUntil(() => link.MAV.cs.rcoverridech1 == 1000, 10000))
            throw new InvalidOperationException("Never observed changed input");
        joy.Available = false;
        if (!joy.SawLoss.WaitOne(10000))
            throw new InvalidOperationException("The polling loop did not observe device loss");
        joy.Input.X = 65535;
        Console.WriteLine("CONFIRMED_INVALID ENABLED={0} CH1={1} CH3={2}", joy.enabled,
                          link.MAV.cs.rcoverridech1, link.MAV.cs.rcoverridech3);
        joy.clearRCOverride();
        Console.WriteLine("CONFIRMED_CLEARED ENABLED={0} CH1={1} CH3={2}", joy.enabled,
                          link.MAV.cs.rcoverridech1, link.MAV.cs.rcoverridech3);
        joy.SawLoss.Dispose();
    }
}
