from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'mavproxy_mission_normal'" not in s:
    s=s.replace("'normal', 'drop_one'", "'normal', 'mavproxy_mission_normal', 'mavproxy_mission_drop_ack', 'drop_one'",1)
    s=s.replace("result = {'scope': (", "result = {'scope': ('Disposable Copter SITL; MAVProxy mission upload with optional dropped ACK' if case.startswith('mavproxy_mission_') else\n                    ",1)
    needle="        if case == 'terrain_drop_one' and direction == 'to_sitl' and msgid == 134:\n"
    insertion='''        if case == 'mavproxy_mission_drop_ack' and direction == 'to_client' and msgid == 47:
            files['dropped'].write(packet)
            result['dropped_mission_acks'] = result.get('dropped_mission_acks', 0) + 1
            continue
'''
    assert s.count(needle)==1
    s=s.replace(needle,insertion+needle)
    p.write_text(s)
