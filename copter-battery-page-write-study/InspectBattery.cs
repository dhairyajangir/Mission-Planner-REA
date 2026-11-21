using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using Mono.Cecil;
using Mono.Cecil.Cil;

public class InspectBattery
{
    static IEnumerable<TypeDefinition> Walk(TypeDefinition type)
    {
        yield return type;
        foreach (var child in type.NestedTypes)
            foreach (var nested in Walk(child)) yield return nested;
    }

    static void Dump(MethodDefinition method, Func<Instruction,bool> match, int before, int after)
    {
        var il = method.Body.Instructions;
        var offsets = new SortedSet<int>();
        for (int i = 0; i < il.Count; i++)
            if (match(il[i]))
                for (int j = Math.Max(0, i-before); j <= Math.Min(il.Count-1,i+after); j++) offsets.Add(j);
        if (offsets.Count == 0) return;
        Console.WriteLine("\n" + method.FullName);
        int previous = -1;
        foreach (int index in offsets)
        {
            if (index > previous+1) Console.WriteLine("...");
            Console.WriteLine(il[index]);
            previous=index;
        }
    }

    static bool Has(Instruction i, params string[] names)
    {
        var value = Convert.ToString(i.Operand);
        return names.Any(n => value.IndexOf(n,StringComparison.Ordinal) >= 0);
    }

    static void Main(string[] args)
    {
        System.Threading.Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
        foreach (var file in args)
        using (var binary = AssemblyDefinition.ReadAssembly(file))
        {
            Console.WriteLine("\nAssembly " + binary.Name.Name + " MVID " + binary.MainModule.Mvid);
            foreach (var t in binary.MainModule.Types.SelectMany(Walk))
            foreach (var m in t.Methods.Where(x => x.HasBody))
            {
                if (t.Name == "ConfigBatteryMonitoring")
                {
                    if (m.Name == "Activate") Dump(m,i=>Has(i,"::startup","::CMB_batmontype_SelectedIndexChanged","::CMB_batmonsensortype_SelectedIndexChanged","::Start()"),1,1);
                    if (m.Name == "InitializeComponent") Dump(m,i=>Has(i,"::TXT_divider_Validated","::TXT_measuredvoltage_Validated","::timer1_Tick","::CMB_batmonsensortype_SelectedIndexChanged"),2,2);
                    if (m.Name == "CMB_batmonsensortype_SelectedIndexChanged") Dump(m,i=>Has(i,"::TXT_ampspervolt_Validated","::TXT_divider_Validated","::startup"),7,2);
                    if (new[]{"TXT_divider_Validated","timer1_Tick","Deactivate"}.Contains(m.Name)) Dump(m,i=>true,0,0);
                }
                if (t.Name == "MAVLinkParam" && new[]{"GetValue","RoundToSignificantDigits","ToString"}.Contains(m.Name)) Dump(m,i=>true,0,0);
                if (t.FullName.Contains("MAVLinkInterface") && (t.Name.Contains("<setParamAsync>") || m.Name == "setParamAsync"))
                    Dump(m,i=>Has(i,"MAVLinkParam::get_Value","::lastparamset"),4,7);
                if (t.FullName.Contains("MAVLinkInterface") && m.Body.Instructions.Any(i=>Has(i,"::lastparamset")) && !t.Name.Contains("<setParamAsync>"))
                    Dump(m,i=>Has(i,"::lastparamset","::AddSeconds","autoparamcommit") || (i.Operand is int && (int)i.Operand == 245),5,7);
            }
        }
        var ma = args.Select(a=>Assembly.LoadFrom(a)).FirstOrDefault(a=>a.GetType("MAVLink+MAVLinkParam")!=null);
        if (ma==null) throw new Exception("No MAVLinkParam in selected assemblies");
        var p = ma.GetType("MAVLink+MAVLinkParam");
        var ctor = p.GetConstructors().Single(c=>c.GetParameters().Length == 4 && c.GetParameters()[1].ParameterType == typeof(double));
        var real = Enum.Parse(ctor.GetParameters()[2].ParameterType,"REAL32");
        foreach (float f in new float[]{10.1f,17f})
        {
            var obj=ctor.Invoke(new object[]{"TEST", (double)f,real,null});
            var stored=(double)p.GetProperty("Value").GetValue(obj,null);
            var s=obj.ToString();
            var parsed=float.Parse(s);
            Console.WriteLine("wire={0} publicValue={1:R} text={2} promotedParsed={3:R} equalDouble={4} outgoingWire={5}",
                BitConverter.ToString(BitConverter.GetBytes(f)),stored,s,(double)parsed,stored==parsed,BitConverter.ToString(BitConverter.GetBytes(parsed)));
        }
    }
}
