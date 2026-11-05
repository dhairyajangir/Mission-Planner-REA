// Compare symbolic IL across a test-only Cecil rewrite, ignoring metadata token
// numbering. This is not a proof of runtime equivalence.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Mono.Cecil;
using Mono.Cecil.Cil;

public static class CompareManagedBodies
{
    private static IEnumerable<TypeDefinition> Types(IEnumerable<TypeDefinition> roots)
    {
        foreach (var t in roots)
        {
            yield return t;
            foreach (var n in Types(t.NestedTypes)) yield return n;
        }
    }

    private static string Operand(object operand)
    {
        if (operand == null) return "";
        var method = operand as MethodReference;
        if (method != null) return "method:" + method.FullName;
        var field = operand as FieldReference;
        if (field != null) return "field:" + field.FullName;
        var type = operand as TypeReference;
        if (type != null) return "type:" + type.FullName;
        var instruction = operand as Instruction;
        if (instruction != null) return "offset:" + instruction.Offset;
        var targets = operand as Instruction[];
        if (targets != null) return "offsets:" + String.Join(",", targets.Select(x => x.Offset.ToString()).ToArray());
        var parameter = operand as ParameterDefinition;
        if (parameter != null) return "param:" + parameter.Index;
        var variable = operand as VariableDefinition;
        if (variable != null) return "local:" + variable.Index;
        var formattable = operand as IFormattable;
        return formattable != null ? formattable.ToString(null, CultureInfo.InvariantCulture) : operand.ToString();
    }

    private static string Hash(MethodDefinition method)
    {
        if (!method.HasBody) return "NO_BODY";
        var b = new StringBuilder();
        b.AppendLine("init=" + method.Body.InitLocals);
        foreach (var v in method.Body.Variables) b.AppendLine("local=" + v.VariableType.FullName);
        foreach (var i in method.Body.Instructions) b.AppendLine(i.OpCode.Code + "|" + Operand(i.Operand));
        foreach (var e in method.Body.ExceptionHandlers)
            b.AppendLine("handler=" + e.HandlerType + ":" + (e.CatchType == null ? "" : e.CatchType.FullName) + ":" +
                (e.TryStart == null ? -1 : e.TryStart.Offset) + ":" + (e.TryEnd == null ? -1 : e.TryEnd.Offset) + ":" +
                (e.HandlerStart == null ? -1 : e.HandlerStart.Offset) + ":" + (e.HandlerEnd == null ? -1 : e.HandlerEnd.Offset) + ":" +
                (e.FilterStart == null ? -1 : e.FilterStart.Offset));
        using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(b.ToString()))).Replace("-", "");
    }

    public static int Main(string[] args)
    {
        using (var a = AssemblyDefinition.ReadAssembly(args[0]))
        using (var b = AssemblyDefinition.ReadAssembly(args[1]))
        {
            var left = Types(a.MainModule.Types).SelectMany(x => x.Methods).ToDictionary(x => x.FullName, Hash);
            var right = Types(b.MainModule.Types).SelectMany(x => x.Methods).ToDictionary(x => x.FullName, Hash);
            Console.WriteLine("LEFT_METHODS=" + left.Count);
            Console.WriteLine("RIGHT_METHODS=" + right.Count);
            var changes = left.Keys.Union(right.Keys).Where(k => !left.ContainsKey(k) || !right.ContainsKey(k) || left[k] != right[k]).OrderBy(k => k).ToArray();
            Console.WriteLine("SYMBOLIC_IL_DIFFERENCES=" + changes.Length);
            foreach (var k in changes) Console.WriteLine("DIFF=" + k);
        }
        return 0;
    }
}
