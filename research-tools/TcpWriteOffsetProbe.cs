// Test the distributed TCP implementation's byte-array offset handling.
using System;
using System.Text;
using MissionPlanner.Comms;
public static class TcpWriteOffsetProbe
{
    public static int Main(string[] args)
    {
        var tcp = new TcpSerial { Host = "127.0.0.1", Port = args[0] };
        try
        {
            tcp.Open();
            byte[] data = Encoding.ASCII.GetBytes("ABCDEFG");
            tcp.Write(data, 2, 3);
            Console.WriteLine("REQUESTED_OFFSET=2 LENGTH=3 EXPECTED_SLICE=CDE");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { tcp.Close(); }
    }
}
