// Original TcpSerial against a local peer that resets the first connection.
using System;
using System.Text;
using System.Threading;
using MissionPlanner.Comms;

public static class TcpAutoReconnectProbe
{
    public static int Main(string[] args)
    {
        var tcp = new TcpSerial { Host = "127.0.0.1", Port = args[0], autoReconnect = true };
        try
        {
            tcp.Open();
            tcp.client.ReceiveTimeout = 3000;
            byte[] buffer = new byte[32];
            int n = tcp.Read(buffer, 0, 5);
            Console.WriteLine("FIRST=" + Encoding.ASCII.GetString(buffer, 0, n));
            tcp.Write(new byte[] { 88 }, 0, 1);
            Thread.Sleep(500);
            Console.WriteLine("BEFORE_RESET_READ_OPEN=" + tcp.IsOpen);
            try { Console.WriteLine("RESET_READ=" + tcp.Read(buffer, 0, buffer.Length)); }
            catch (Exception ex) { Console.WriteLine("RESET_READ_ERROR=" + ex.Message); }
            var deadline = DateTime.UtcNow.AddSeconds(15);
            bool connected = false;
            while (DateTime.UtcNow < deadline)
            {
                if (tcp.IsOpen) { connected = true; break; }
                Thread.Sleep(100);
            }
            Console.WriteLine("AUTO_CONNECTED=" + connected);
            if (connected)
            {
                tcp.client.ReceiveTimeout = 3000;
                n = tcp.Read(buffer, 0, 6);
                Console.WriteLine("SECOND=" + Encoding.ASCII.GetString(buffer, 0, n));
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { tcp.Close(); }
    }
}
