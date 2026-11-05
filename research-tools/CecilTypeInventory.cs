// Read CLI metadata without loading or executing the target assembly.
using System;
using Mono.Cecil;

public static class CecilTypeInventory
{
    static void Print(TypeDefinition type)
    {
        Console.WriteLine(type.MetadataToken.ToUInt32().ToString("X8") + "\t" + type.FullName + "\t" +
                          type.Name + "\t" + (type.DeclaringType == null ? "top" : "nested") + "\t" + type.Methods.Count);
        foreach (var nested in type.NestedTypes) Print(nested);
    }
    public static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        using (var assembly = AssemblyDefinition.ReadAssembly(args[0]))
            foreach (var type in assembly.MainModule.Types) Print(type);
        return 0;
    }
}
