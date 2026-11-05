// Synthetic keys and disposable disarmed SITL; no real key store is loaded.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Mavlink;
using MissionPlanner.Utilities;
public static class SigningDiscoveryProbe {
    static byte[] StateKey(MAVLinkInterface port) {
        return (byte[])typeof(MAVState).GetField("signingKey",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(port.MAVlist[1,1]);
    }
    public static int Main(string[] args) {
        MAVLinkInterface port=null;
        try {
            Settings.CustomUserDataDirectory=Path.Combine(args[1],"isolated-user-data");
            Directory.CreateDirectory(Settings.GetUserDataDirectory());
            log4net.Config.BasicConfigurator.Configure();
            MAVAuthKeys.Keys.Clear();
            MAVAuthKeys.AddKey("wrong", "synthetic-wrong-key");
            if (args[2]=="match") MAVAuthKeys.AddKey("correct", "synthetic-signing-seed");
            Console.WriteLine("CASE="+args[2]+" KEY_CANDIDATES="+MAVAuthKeys.Keys.Count);
            port=new MAVLinkInterface { BaseStream = new TcpSerial { Host="127.0.0.1", Port=args[0] } };
            port.Open(false,false,false);
            Console.WriteLine("OPEN="+port.BaseStream.IsOpen+" SELECTED="+port.sysidcurrent+":"+port.compidcurrent);
            System.Threading.Thread.Sleep(8000);
            Console.WriteLine("BEFORE="+port.GetParam("LOG_DISARMED"));
            bool setup=port.setupSigning(1,1,"synthetic-signing-seed");
            Console.WriteLine("SETUP="+setup+" STATE_KEY_NULL="+(StateKey(port)==null));
            var deadline=DateTime.UtcNow.AddSeconds(6);
            while (DateTime.UtcNow<deadline && StateKey(port)==null) {
                if(port.BaseStream.BytesToRead>0) port.readPacket(); else System.Threading.Thread.Sleep(5);
            }
            var adopted=StateKey(port);
            byte[] expected;
            using(var hash=SHA256.Create()) expected=hash.ComputeHash(Encoding.UTF8.GetBytes("synthetic-signing-seed"));
            Console.WriteLine("ADOPTED="+(adopted!=null && adopted.SequenceEqual(expected))+" KEY_NULL="+(adopted==null));
            try { Console.WriteLine("AFTER="+port.GetParam("LOG_DISARMED")); }
            catch(Exception ex) { Console.WriteLine("AFTER_ERROR="+ex.GetType().FullName+":"+ex.Message); }
            Console.WriteLine("DISCOVERY_PROBE_COMPLETE=True"); return 0;
        } catch(Exception ex) { Console.WriteLine("ERROR="+ex); return 1; }
        finally { if(port!=null)port.Close(); }
    }
}
