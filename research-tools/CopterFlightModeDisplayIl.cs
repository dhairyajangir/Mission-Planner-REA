// Metadata-only decoder. Reference research-tools/Mono.Cecil.dll when compiling.
using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Mono.Cecil;

public static class CopterFlightModeDisplayIl
{
    public static void Main(string[] args)
    {
        string hash;
        using (var stream = File.OpenRead(args[0]))
        using (var sha = SHA256.Create())
            hash = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        if (hash != "a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a")
            throw new InvalidDataException("Unexpected MissionPlanner.exe: " + hash);

        using (var assembly = AssemblyDefinition.ReadAssembly(args[0]))
        {
            Console.WriteLine("Assembly SHA-256 " + hash);
            Console.WriteLine("Module version ID " + assembly.MainModule.Mvid);
            var page = assembly.MainModule.GetType("MissionPlanner.GCSViews.ConfigurationView.ConfigFlightModes");
            foreach (var name in new[] { "readSwitch", "timer_Tick" })
            {
                var method = page.Methods.Single(m => m.Name == name);
                Console.WriteLine();
                Console.WriteLine("{0} [0x{1:x8}]", method.FullName, method.MetadataToken.ToUInt32());
                foreach (var instruction in method.Body.Instructions)
                    Console.WriteLine(instruction);
            }
        }
    }
}
