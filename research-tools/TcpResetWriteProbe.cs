// Synthetic localhost reset; observe one TcpSerial.Write call.
using System;
using System.Text;
using System.Threading;
using MissionPlanner.Comms;
public static class TcpResetWriteProbe
{
    public static int Main(string[] args)
    {
        var tcp = new TcpSerial { Host = "127.0.0.1", Port = args[0] };
        try
        {
            tcp.Open();
            tcp.client.ReceiveTimeout = 3000;
            byte[] buffer = new byte[5];
            int n = tcp.Read(buffer, 0, buffer.Length);
            Console.WriteLine("FIRST=" + Encoding.ASCII.GetString(buffer, 0, n));
            tcp.Write(new byte[] { 88 }, 0, 1);
            Thread.Sleep(500);
            Console.WriteLine("BEFORE_WRITE_OPEN=" + tcp.IsOpen);
            try { tcp.Write(new byte[] { 89 }, 0, 1); Console.WriteLine("WRITE_RETURNED"); }
            catch (Exception ex) { Console.WriteLine("WRITE_ERROR=" + ex.Message); }
            Console.WriteLine("AFTER_WRITE_OPEN=" + tcp.IsOpen);
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { tcp.Close(); }
    }
}
