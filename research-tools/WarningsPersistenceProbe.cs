using System;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;
using MissionPlanner.Utilities;
using MissionPlanner.Warnings;

public class WarningFixtureState
{
    public double Voltage { get; set; }
    public bool Armed { get; set; }
}

public static class WarningsPersistenceProbe
{
    public static void Main(string[] args)
    {
        string libraries = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs e) {
            string path = Path.Combine(libraries, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(path) ? Assembly.LoadFrom(path) : null;
        };
        Run(libraries, Path.GetFullPath(args[1]), args[2]);
    }

    private static void Expect(bool result, string label)
    {
        if (!result) throw new InvalidOperationException(label);
        Console.WriteLine("PASS " + label);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Run(string libraries, string profile, string phase)
    {
        Settings.CustomUserDataDirectory = profile;
        Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        string expectedFolder = Path.Combine(profile, Settings.AppConfigName);
        Directory.CreateDirectory(expectedFolder);
        Expect(typeof(WarningEngine).Assembly.Location == Path.Combine(libraries, "MissionPlanner.Utilities.dll"),
            "loaded portable utility assembly");
        var state = new WarningFixtureState { Voltage = 9.5, Armed = true };
        CustomWarning.defaultsrc = state;
        Expect(WarningEngine.warningconfigfile == Path.Combine(expectedFolder, "warnings.xml"), "disposable settings path");

        const string text = "Battery < {warning} & armed: {value}";
        if (phase == "save")
        {
            Expect(WarningEngine.warnings.Count == 0 && !File.Exists(WarningEngine.warningconfigfile),
                "empty first startup");
            var parent = new CustomWarning { Name = "Voltage", ConditionType = CustomWarning.Conditional.LT,
                Warning = 10.75, RepeatTime = 30, Text = text, type = CustomWarning.WarningType.Coloring, color = "Gold" };
            parent.Child = new CustomWarning { Name = "Armed", ConditionType = CustomWarning.Conditional.EQ, Warning = 1 };
            WarningEngine.warnings.Add(parent);
            WarningEngine.SaveConfig();
            Expect(File.Exists(WarningEngine.warningconfigfile), "SaveConfig wrote warnings.xml");
            return;
        }
        if (phase != "load") throw new ArgumentException("Expected save or load");
        Expect(WarningEngine.warnings.Count == 1, "fresh engine loaded one rule automatically");
        var rule = WarningEngine.warnings[0];
        Expect(rule.Name == "Voltage" && rule.ConditionType == CustomWarning.Conditional.LT
            && rule.Warning == 10.75 && rule.RepeatTime == 30 && rule.Text == text
            && rule.type == CustomWarning.WarningType.Coloring && rule.color == "Gold", "restored parent settings");
        Expect(rule.Child != null && rule.Child.Name == "Armed"
            && rule.Child.ConditionType == CustomWarning.Conditional.EQ && rule.Child.Warning == 1,
            "restored child settings");
        Expect(rule.CheckValue(false) && rule.Child.CheckValue(false)
            && rule.SayText() == "Battery < 10.75 & armed: 9.5", "restored rule reads both synthetic fields");
        state.Armed = false;
        Expect(rule.CheckValue(false) && !rule.Child.CheckValue(false), "restored child follows field changes");
        state.Voltage = 11.25;
        Expect(!rule.CheckValue(false), "restored parent follows field changes");
    }
}
