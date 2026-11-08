"""Independent observer of a disposable ArduCopter SITL (WSL, pymavlink): connects to SERIAL1 (tcp 5762), asks for SERVO_OUTPUT_RAW at 10 Hz,
and writes one CSV row per message with the wall-clock time (UTC epoch seconds) and servo1..servo8 raw PWM, plus any STATUSTEXT lines.
It is passive apart from the message-interval request and is used while Mission Planner drives the motor-test page on SERIAL0 (tcp 5760).

    python sitl-servo-observer.py <seconds to record> <out csv> [port]
"""
import csv
import sys
import time

from pymavlink import mavutil

secs, out = float(sys.argv[1]), sys.argv[2]
port = sys.argv[3] if len(sys.argv) > 3 else '5762'
m = None
t0 = time.time()
while time.time() - t0 < 180 and m is None:      # SERIAL1 only exists after a client has connected to SERIAL0
    try:
        m = mavutil.mavlink_connection('tcp:127.0.0.1:' + port, autoreconnect=False)
    except Exception:
        time.sleep(0.5)
if m is None:
    print('could not connect to port', port)
    sys.exit(1)
m.wait_heartbeat(timeout=60)
m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 100000, 0, 0, 0, 0, 0)
with open(out, 'w', newline='') as f, open(out + '.statustext.txt', 'w') as g:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['utc_epoch', 'servo1', 'servo2', 'servo3', 'servo4', 'servo5', 'servo6', 'servo7', 'servo8'])
    end = time.time() + secs
    n = 0
    while time.time() < end:
        msg = m.recv_match(type=['SERVO_OUTPUT_RAW', 'STATUSTEXT'], blocking=True, timeout=1)
        if msg is None:
            continue
        if msg.get_type() == 'SERVO_OUTPUT_RAW':
            w.writerow(['%.3f' % time.time(), msg.servo1_raw, msg.servo2_raw, msg.servo3_raw, msg.servo4_raw, msg.servo5_raw, msg.servo6_raw, msg.servo7_raw, msg.servo8_raw])
            n += 1
        else:
            g.write('%.3f %s\n' % (time.time(), msg.text))
print('rows', n)
