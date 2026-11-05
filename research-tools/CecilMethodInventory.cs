// Static metadata and IL method-reference instructions. Does not execute target code.
using System;
using System.Text;
using Mono.Cecil;
using Mono.Cecil.Cil;

public static class CecilMethodInventory
{
    static string Enc(string value) { return Convert.ToBase64String(Encoding.UTF8.GetBytes(value ?? "")); }
    static string Token(IMetadataTokenProvider item) { return item.MetadataToken.ToUInt32().ToString("X8"); }
    static void Print(TypeDefinition type)
    {
        foreach (var method in type.Methods)
        {
            Console.WriteLine("M\t" + Token(method) + "\t" + Token(type) + "\t" + Enc(method.FullName) +
                "\t" + (method.HasBody ? "1" : "0") + "\t" + (method.HasBody ? method.Body.Instructions.Count : 0));
            if (!method.HasBody) continue;
            foreach (var instruction in method.Body.Instructions)
            {
                var target = instruction.Operand as MethodReference;
                if (target == null) continue;
                Console.WriteLine("C\t" + Token(method) + "\t" + instruction.Offset + "\t" +
                    Enc(instruction.OpCode.Name) + "\t" + Enc(target.FullName));
            }
        }
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
