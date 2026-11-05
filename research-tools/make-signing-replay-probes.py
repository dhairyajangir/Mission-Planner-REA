from pathlib import Path
root=Path(__file__).resolve().parent.parent
relay=(root/'research-tools/signing-serial1-relay.py').read_text()
relay=relay.replace("('signing-serial1-'+mode)","('signing-serial1-replay-'+mode)")
needle="    client,_=listener.accept();client.setblocking(False);secondary.setblocking(False)\n"
replace='''    client,_=listener.accept();client.setblocking(False);secondary.setblocking(False)
    sample=bytes.fromhex(result['configured_secondary']['raw_hex'])
    altered=sample[:-1]+bytes([sample[-1]^1])
    injected=sample+sample+altered
    client.sendall(injected);files['downlink'].write(injected);files['downlink'].flush()
    (out/'injected.bin').write_bytes(injected)
    result['injected_sample_sha256']=hashlib.sha256(sample).hexdigest()
    result['injected_bad_sha256']=hashlib.sha256(altered).hexdigest()
'''
assert relay.count(needle)==1
(root/'research-tools/signing-serial1-replay-relay.py').write_text(relay.replace(needle,replace))
source=(root/'research-tools/SigningSerial1Probe.cs').read_text()
source=source.replace('SigningSerial1Probe','SigningSerial1ReplayProbe')
needle='            try { port.Open(false,false,false);'
addition='''            port.OnPacketReceived += (sender,message) => {
                if(message.msgid==(uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT && message.buffer!=null) {
                    using(var digest=SHA256.Create()) Console.WriteLine("HB_SHA="+BitConverter.ToString(digest.ComputeHash(message.buffer)).Replace("-","").ToLowerInvariant());
                }
            };
'''
assert source.count(needle)==1
source=source.replace(needle,addition+needle)
(root/'research-tools/SigningSerial1ReplayProbe.cs').write_text(source)
