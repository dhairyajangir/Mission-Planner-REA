from pathlib import Path
p = Path('sitl-evidence/command-ack-relay.py')
s = p.read_text(encoding='utf-8')
old = "if case not in ('plane_guided',"
assert s.count(old) == 1
s = s.replace(old, "if case not in ('plane_guided_drop_one', 'plane_guided_drop_all', 'plane_guided',", 1)
old = "case == 'plane_guided'"
assert s.count(old) == 3
s = s.replace(old, "case.startswith('plane_guided')")
old = "        if case in ('mavproxy_mission_drop_ack','mavproxy_mission_drop_ack_retry')"
assert s.count(old) == 1
addition = """        if case in ('plane_guided_drop_one', 'plane_guided_drop_all') and direction == 'to_client' and msgid == 47 and (case == 'plane_guided_drop_all' or result.get('dropped_mission_acks', 0) == 0):
            files['dropped'].write(packet)
            result['dropped_mission_acks'] = result.get('dropped_mission_acks', 0) + 1
            continue
"""
s = s.replace(old, addition + old, 1)
p.write_text(s, encoding='utf-8')
