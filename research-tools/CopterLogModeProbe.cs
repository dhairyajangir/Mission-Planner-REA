// Offline DataFlash label probe for the archived 1.3.83 binaries.
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Xml.Linq;

class CopterLogModeProbe
{
    static void Fixed(BinaryWriter writer, string text, int length)
    {
        byte[] bytes = new byte[length];
        Encoding.ASCII.GetBytes(text).CopyTo(bytes, 0);
        writer.Write(bytes);
    }

    static void Header(BinaryWriter writer, byte type)
    {
        writer.Write(new byte[] { 0xA3, 0x95, type });
    }

    static void Format(BinaryWriter writer, byte type, byte length, string name, string format, string fields)
    {
        Header(writer, 128);
        writer.Write(type);
        writer.Write(length);
        Fixed(writer, name, 4);
        Fixed(writer, format, 16);
        Fixed(writer, fields, 64);
    }

    static void Mode(BinaryWriter writer, byte number, ulong time)
    {
        Header(writer, 123);
        writer.Write(time);
        writer.Write(number);
        writer.Write(number);
        writer.Write((byte)0);
    }

    static void Main(string[] args)
    {
        string release = Path.GetFullPath(args[0]);
        string dir = Path.GetFullPath(args[1]);
        Directory.CreateDirectory(dir);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) => {
            string path = Path.Combine(release, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(path) ? Assembly.LoadFrom(path) : null;
        };
        var utilities = Assembly.LoadFrom(Path.Combine(release, "MissionPlanner.Utilities.dll"));
        var app = Assembly.LoadFrom(Path.Combine(release, "MissionPlanner.exe"));
        var repository = utilities.GetType("MissionPlanner.Utilities.ParameterMetaDataRepository", true);
        var flags = BindingFlags.NonPublic | BindingFlags.Static;
        var cache = repository.GetField("_cache", flags).GetValue(null);
        var node = XDocument.Load(Path.Combine(release, "ParameterMetaDataBackup.xml"))
                            .Root.Element("ArduCopter2").Element("FLTMODE1").Element("Values");
        // Seed the normal cache to test exactly one metadata source without refreshing online.
        string key = "FLTMODE1ValuesArduCopter2";
        object entry = cache.GetType().GetMethod("CreateEntry").Invoke(cache, new object[] { key });
        entry.GetType().GetProperty("Value").SetValue(entry, node.Value, null);
        ((IDisposable)entry).Dispose();
        object[] lookup = { key, null };
        if (!(bool) cache.GetType().GetMethod("TryGetValue").Invoke(cache, lookup)
            || !node.Value.Equals(lookup[1])) throw new Exception("Unable to seed bundled metadata");
        var modeCallback = (MethodInfo)app.ManifestModule.ResolveMethod(0x06000232);
        if (modeCallback.Name != "<OnLoad>b__142_3") throw new Exception("Unexpected application callback");
        var receiver = Activator.CreateInstance(modeCallback.DeclaringType, true);
        var binary = utilities.GetType("MissionPlanner.Utilities.BinaryLog", true);
        var evt = binary.GetEvent("onFlightMode");
        var handler = Delegate.CreateDelegate(evt.EventHandlerType, receiver, modeCallback);
        var convert = binary.GetMethod("ConvertBin");
        string input = Path.Combine(dir, "mode-series.bin");
        using (var file = new BinaryWriter(File.Open(input, FileMode.CreateNew))) {
            Format(file, 123, 14, "MODE", "QMBB", "TimeUS,Mode,ModeNum,Rsn");
            Format(file, 75, 75, "MSG", "QZ", "TimeUS,Message");
            // First record precedes a Copter firmware marker. The same ID recurs after it.
            Mode(file, 5, 1);
            Header(file, 75);
            file.Write((ulong)2);
            Fixed(file, "ArduCopter V4.8.0-dev (72b23820)", 64);
            for (byte n = 0; n <= 30; n++) Mode(file, n, (ulong)(3 + n));
        }
        foreach (string variant in new[] { "without-handler", "with-handler" }) {
            if (variant == "with-handler") evt.AddEventHandler(null, handler);
            string output = Path.Combine(dir, variant + ".log");
            convert.Invoke(null, new object[] { input, output, null });
            Console.WriteLine(variant + " lines=" + File.ReadAllLines(output).Length);
        }
        Console.WriteLine("callback=" + modeCallback.DeclaringType.FullName + "." + modeCallback.Name);
    }
}
