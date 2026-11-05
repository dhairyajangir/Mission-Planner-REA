// Synthetic signing key on a disposable, disarmed SITL connection only.
using System;
using System.Linq;
using System.Reflection;
using MissionPlanner;
using MissionPlanner.Comms;
public static class SigningSitlProbe {
    public static int Main(string[] args) {
        MAVLinkInterface port=null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port=new MAVLinkInterface { BaseStream = new TcpSerial { Host="127.0.0.1", Port=args[0] } };
            port.Open(false,false,false);
            Console.WriteLine("OPEN="+port.BaseStream.IsOpen+" SELECTED="+port.sysidcurrent+":"+port.compidcurrent);
            System.Threading.Thread.Sleep(8000);
            Console.WriteLine("BEFORE="+port.GetParam("LOG_DISARMED"));
            byte[] key=Enumerable.Range(0,32).Select(x=>(byte)x).ToArray();
            bool enabled=port.setupSigning(1,1,"",key);
            typeof(MAVState).GetField("signingKey",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(port.MAVlist[1,1],key);
            Console.WriteLine("SETUP_RETURN="+enabled+" STATE_SIGNING="+port.MAVlist[1,1].signing);
            System.Threading.Thread.Sleep(1500);
            Console.WriteLine("AFTER="+port.GetParam("LOG_DISARMED"));
            Console.WriteLine("SIGNING_SITL_COMPLETE=True");
            return 0;
        } catch(Exception e) { Console.WriteLine("ERROR="+e); return 1; }
        finally { if(port!=null)port.Close(); }
    }
}
