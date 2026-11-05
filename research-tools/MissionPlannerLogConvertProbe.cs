// Calls the original Mission Planner utility DLL on the captured simulator log.
using System;
using System.IO;
using MissionPlanner.Utilities;

class MissionPlannerLogConvertProbe
{
    static int Main(string[] args)
    {
        if (args.Length != 2 || File.Exists(args[1])) return 2;
        try
        {
            BinaryLog.ConvertBin(args[0], args[1]);
            Console.WriteLine("CONVERT_OUTPUT_BYTES=" + new FileInfo(args[1]).Length);
            return 0;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine(e);
            return 1;
        }
    }
}
