"""Which of the given parameter names does a running disposable SITL answer for? Used to explain why a Mission Planner setup page that checks for a parameter in
Activate() disables itself. Prints one line per name: present with its value, or absent (no PARAM_VALUE after 5 requests).

    python sitl-param-presence.py <tcp port> <name> [name ...]
"""
import sys
import time

from pymavlink import mavutil

port, names = sys.argv[1], sys.argv[2:]
m = None
t0 = time.time()
while m is None and time.time() - t0 < 60:
    try:
        m = mavutil.mavlink_connection('tcp:127.0.0.1:' + port, autoreconnect=False)
        m.wait_heartbeat(timeout=30)
    except Exception:
        m = None
        time.sleep(1)
if m is None:
    sys.exit('no connection')
for name in names:
    value = None
    for _ in range(5):
        m.mav.param_request_read_send(m.target_system, m.target_component, name.encode(), -1)
        r = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
        if r is not None and r.param_id.rstrip('\x00') == name:
            value = r.param_value
            break
    print('%s: %s' % (name, 'present, value %s' % value if value is not None else 'absent'))
