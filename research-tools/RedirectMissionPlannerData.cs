// Test-only patch: isolate Mission Planner's shared and user data directories.
// The original portable distribution is left untouched.
using System;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

public static class RedirectMissionPlannerData
{
    public static int Main(string[] args)
    {
        if (args.Length != 3) throw new ArgumentException("Expected source DLL, output DLL, data directory");
        var source = Path.GetFullPath(args[0]);
        var output = Path.GetFullPath(args[1]);
        var data = Path.GetFullPath(args[2]).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        Directory.CreateDirectory(data);
        using (var assembly = AssemblyDefinition.ReadAssembly(source, new ReaderParameters { InMemory = true }))
        {
            var type = assembly.MainModule.GetType("MissionPlanner.Utilities.Settings");
            if (type == null) throw new InvalidOperationException("Settings type not found");
            foreach (var name in new[] { "GetDataDirectory", "GetUserDataDirectory" })
            {
                var matches = type.Methods.Where(m => m.Name == name && !m.HasParameters && m.ReturnType.FullName == "System.String").ToArray();
                if (matches.Length != 1) throw new InvalidOperationException("Unexpected method count for " + name);
                var method = matches[0];
                method.Body.ExceptionHandlers.Clear();
                method.Body.Variables.Clear();
                method.Body.Instructions.Clear();
                var il = method.Body.GetILProcessor();
                il.Append(il.Create(OpCodes.Ldstr, data));
                il.Append(il.Create(OpCodes.Ret));
                Console.WriteLine("Redirected " + name + " to test data directory");
            }
            assembly.Write(output);
        }
        return 0;
    }
}
