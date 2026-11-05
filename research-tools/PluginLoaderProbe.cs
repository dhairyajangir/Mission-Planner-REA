using System;
using System.IO;
using System.Linq;
using System.Reflection;
using MissionPlanner.Plugin;

public static class PluginLoaderProbe
{
    public static int Main(string[] args)
    {
        try
        {
            if (args.Length != 2) throw new ArgumentException("fixture and disabled-copy paths required");
            var eventPath = Environment.GetEnvironmentVariable("MP_PLUGIN_EVENTS");
            if (String.IsNullOrEmpty(eventPath) || File.Exists(eventPath))
                throw new InvalidOperationException("fresh event path required");
            log4net.Config.BasicConfigurator.Configure();
            PluginLoader.DisabledPluginNames.Add(Path.GetFileName(args[1]).ToLowerInvariant());
            PluginLoader.Load(Path.GetFullPath(args[1]));
            Console.WriteLine("DISABLED_EVENTS=" + (File.Exists(eventPath) ? File.ReadAllLines(eventPath).Length : 0));
            PluginLoader.DisabledPluginNames.Clear();
            PluginLoader.Load(Path.GetFullPath(args[0]));
            Console.WriteLine("PENDING=" + String.Join(",", PluginLoader.LoadingPlugins.Select(x => x.Name).OrderBy(x => x)));
            var method = typeof(PluginLoader).GetMethod("PluginInit", BindingFlags.NonPublic | BindingFlags.Static);
            if (method == null) throw new MissingMethodException("PluginInit");
            method.Invoke(null, null);
            Console.WriteLine("ACTIVE=" + String.Join(",", PluginLoader.Plugins.Select(x => x.Name).OrderBy(x => x)));
            Console.WriteLine("PENDING_AFTER=" + PluginLoader.LoadingPlugins.Count);
            if (PluginLoader.Plugins.Count != 1 || PluginLoader.Plugins[0].Name != "AcceptedFixture") return 3;
            // Direct invocation, not the application's scheduler or shutdown path.
            PluginLoader.Plugins[0].Exit();
            Console.WriteLine("EVENTS=" + String.Join("|", File.ReadAllLines(eventPath)));
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            return 1;
        }
    }
}
