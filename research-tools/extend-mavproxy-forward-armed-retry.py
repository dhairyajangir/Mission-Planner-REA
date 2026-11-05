from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'mavproxy_forward_armed_block_retry'" not in s:
    s=s.replace("'mavproxy_forward_armed_block', 'mavproxy_forward_armed_allow'", "'mavproxy_forward_armed_block', 'mavproxy_forward_armed_allow', 'mavproxy_forward_armed_block_retry', 'mavproxy_forward_armed_allow_retry'",1)
    p.write_text(s)
