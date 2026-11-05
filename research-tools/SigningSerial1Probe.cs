// Synthetic in-memory key candidates; isolated workspace settings, disposable SITL.
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
public static class SigningSerial1Probe {
    static byte[] StateKey(MAVLinkInterface port) {
        return (byte[])typeof(MAVState).GetField("signingKey",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(port.MAVlist[1,1]);
    }
    public static int Main(string[] args) {
        MAVLinkInterface port=null;
        try {
            Settings.CustomUserDataDirectory=Path.Combine(args[1],"isolated-user-data");
            Directory.CreateDirectory(Settings.GetUserDataDirectory());
            log4net.Config.BasicConfigurator.Configure();
            MAVAuthKeys.Keys.Clear();MAVAuthKeys.AddKey("wrong","synthetic-wrong-key");
            if(args[2]=="match") MAVAuthKeys.AddKey("correct","synthetic-signing-seed");
            Console.WriteLine("CASE="+args[2]+" CANDIDATES="+MAVAuthKeys.Keys.Count);
            port=new MAVLinkInterface { BaseStream=new TcpSerial { Host="127.0.0.1",Port=args[0] } };
            try { port.Open(false,false,false);Console.WriteLine("OPEN_RETURNED=True ISOPEN="+port.BaseStream.IsOpen+" SELECTED="+port.sysidcurrent+":"+port.compidcurrent); }
            catch(Exception ex) { Console.WriteLine("OPEN_ERROR="+ex.GetType().FullName+":"+ex.Message); }
            var stateKey=StateKey(port);byte[] expected;
            using(var hash=SHA256.Create())expected=hash.ComputeHash(Encoding.UTF8.GetBytes("synthetic-signing-seed"));
            Console.WriteLine("ADOPTED="+(stateKey!=null && stateKey.SequenceEqual(expected))+" KEY_NULL="+(stateKey==null));
            if(port.BaseStream.IsOpen) {
                try { Console.WriteLine("PARAM="+port.GetParam("LOG_DISARMED")); }
                catch(Exception ex) { Console.WriteLine("PARAM_ERROR="+ex.GetType().FullName+":"+ex.Message); }
            }
            Console.WriteLine("SERIAL1_PROBE_COMPLETE=True");return 0;
        } catch(Exception ex) {Console.WriteLine("ERROR="+ex);return 1;}
        finally {if(port!=null)port.Close();}
    }
}
