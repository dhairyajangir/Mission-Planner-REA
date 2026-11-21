using System;
using System.IO;
using System.Reflection;

// Execute the earlier probe unchanged, using the original Settings API to isolate its data.
public static class IsolatedProbe
{
    public static int Main(string[] args)
    {
        string release = Path.GetFullPath(args[0]);
        Assembly utilities = Assembly.LoadFrom(Path.Combine(release, "MissionPlanner.Utilities.dll"));
        Type settings = utilities.GetType("MissionPlanner.Utilities.Settings", true);
        string temporary = Path.Combine(Directory.GetCurrentDirectory(), "user");
        settings.GetField("CustomUserDataDirectory").SetValue(null, temporary);
        string profile = Path.GetFullPath((string)settings.GetMethod("GetUserDataDirectory").Invoke(null, null));
        if (!profile.StartsWith(temporary + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Unexpected settings directory: " + profile);
        Directory.CreateDirectory(profile);
        int code = JoystickMappingProbe.Main(args);
        if (code != 0) return code;
        ConfirmedLifecycle.Run();
        foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            if (!assembly.IsDynamic && !String.IsNullOrEmpty(assembly.Location) &&
                String.Equals(Path.GetDirectoryName(assembly.Location), release, StringComparison.OrdinalIgnoreCase))
                Console.WriteLine("RELEASE_FILE=" + Path.GetFileName(assembly.Location));
        return code;
    }
}
