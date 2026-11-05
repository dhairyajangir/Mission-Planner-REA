using System;
using System.IO;
using MissionPlanner.Plugin;

public abstract class FixtureBase : Plugin
{
    public override string Version { get { return "1"; } }
    public override string Author { get { return "Local test fixture"; } }
    protected void Record(string step)
    {
        File.AppendAllText(Environment.GetEnvironmentVariable("MP_PLUGIN_EVENTS"), Name + ":" + step + "\n");
    }
    public override bool Exit() { Record("Exit"); return true; }
}

public sealed class AcceptedFixture : FixtureBase
{
    public override string Name { get { return "AcceptedFixture"; } }
    public override bool Init() { Record("Init"); return true; }
    public override bool Loaded() { Record("Loaded"); return true; }
}

public sealed class RejectInitFixture : FixtureBase
{
    public override string Name { get { return "RejectInitFixture"; } }
    public override bool Init() { Record("Init"); return false; }
    public override bool Loaded() { Record("Loaded"); return true; }
}

public sealed class RejectLoadedFixture : FixtureBase
{
    public override string Name { get { return "RejectLoadedFixture"; } }
    public override bool Init() { Record("Init"); return true; }
    public override bool Loaded() { Record("Loaded"); return false; }
}

public sealed class ThrowInitFixture : FixtureBase
{
    public override string Name { get { return "ThrowInitFixture"; } }
    public override bool Init() { Record("Init"); throw new InvalidOperationException("synthetic init failure"); }
    public override bool Loaded() { Record("Loaded"); return true; }
}
