// Original TcpSerial against a controlled localhost peer; no vehicle commands.
using System;
using System.Text;
using System.Threading;
using MissionPlanner.Comms;

public static class TcpReconnectProbe
{
    public static int Main(string[] args)
    {
        var tcp = new TcpSerial { Host = "127.0.0.1", Port = args[0] };
        try
        {
            tcp.Open();
            tcp.client.ReceiveTimeout = 3000;
            byte[] buffer = new byte[32];
            int first = tcp.Read(buffer, 0, 5);
            Console.WriteLine("FIRST=" + Encoding.ASCII.GetString(buffer, 0, first));
            tcp.Write(new byte[] { 88 }, 0, 1);
            Thread.Sleep(500);
            Console.WriteLine("AFTER_FIN_BEFORE_READ_OPEN=" + tcp.IsOpen);
            int end = tcp.Read(buffer, 0, buffer.Length);
            Console.WriteLine("EOF_READ=" + end);
            Console.WriteLine("AFTER_EOF_OPEN=" + tcp.IsOpen);
            tcp.Close();
            Console.WriteLine("AFTER_CLOSE_OPEN=" + tcp.IsOpen + " HOST_EMPTY=" + (tcp.Host == ""));
            tcp.Host = "127.0.0.1";
            tcp.Open();
            tcp.client.ReceiveTimeout = 3000;
            int second = tcp.Read(buffer, 0, 6);
            Console.WriteLine("SECOND=" + Encoding.ASCII.GetString(buffer, 0, second));
            Console.WriteLine("REOPENED=" + tcp.IsOpen);
            if (first != 5 || end != 0 || second != 6) throw new InvalidOperationException("unexpected peer exchange");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { tcp.Close(); }
    }
}
