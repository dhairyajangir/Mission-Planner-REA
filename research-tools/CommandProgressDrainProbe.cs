// After COMMAND_INT returns, capture bytes still available on the local test TCP stream.
using System;
using System.IO;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;
public static class CommandProgressDrainProbe
{
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            bool answer = port.doCommandInt(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true);
            Console.WriteLine("INT_RESULT=" + answer);
            Thread.Sleep(250);
            int available = port.BaseStream.BytesToRead;
            byte[] bytes = new byte[available];
            int read = available == 0 ? 0 : port.BaseStream.Read(bytes, 0, available);
            Array.Resize(ref bytes, read);
            File.WriteAllBytes(args[1], bytes);
            Console.WriteLine("DRAIN_BYTES=" + read);
            if (answer) throw new InvalidOperationException("expected false in this fixture");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
