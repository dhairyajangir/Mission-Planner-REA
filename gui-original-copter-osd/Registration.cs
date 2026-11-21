using System;
using System.Linq;
using Mono.Cecil;

public class Registration
{
    public static void Main(string[] args)
    {
        using (var assembly = AssemblyDefinition.ReadAssembly(args[0]))
        {
            var module = assembly.MainModule;
            Console.WriteLine("MVID " + module.Mvid);
            foreach (var entry in new[]{new[]{"InitialSetup","ConfigHWOSD"},new[]{"SoftwareConfig","ConfigOSD"}})
            {
                var type = module.GetType("MissionPlanner.GCSViews." + entry[0]);
                foreach (var method in type.Methods.Where(m => m.HasBody))
                {
                    var il = method.Body.Instructions;
                    for (var i=0; i<il.Count;i++)
                    {
                        if (il[i].OpCode.Name != "ldtoken" || Convert.ToString(il[i].Operand) != "MissionPlanner.GCSViews.ConfigurationView."+entry[1])
                            continue;
                        Console.WriteLine(method.FullName);
                        for (var j=Math.Max(0,i-12);j<Math.Min(i+17,il.Count);j++) Console.WriteLine(il[j]);
                    }
                }
            }
        }
    }
}
