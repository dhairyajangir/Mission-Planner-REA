"""Which of the given parameter names does a running disposable SITL have? Used to explain why a Mission Planner setup page that checks for a parameter in
Activate() disables itself or throws. The whole parameter list is downloaded once (PARAM_REQUEST_LIST) and the names are looked up in it, because asking for
single names one at a time proved unreliable after an unanswered request (see sitl-evidence/setup-page-disabled-reasons/).
Writes the full list next to the answers when a third argument path is given through the environment variable PARAM_DUMP.

    python sitl-param-presence.py <tcp port> <name> [name ...]
"""
import os
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
m.mav.param_request_list_send(m.target_system, m.target_component)
params = {}
count = None
last = time.time()
while time.time() - last < 8 and (count is None or len(params) < count):
    r = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
    if r is None:
        continue
    last = time.time()
    count = r.param_count
    params[r.param_id.rstrip('\x00')] = r.param_value
print('downloaded %d of %s parameters' % (len(params), count))
for name in names:
    print('%s: %s' % (name, 'present, value %s' % params[name] if name in params else 'absent'))
dump = os.environ.get('PARAM_DUMP')
if dump:
    with open(dump, 'w') as f:
        for k in sorted(params):
            f.write('%s,%s\n' % (k, params[k]))
