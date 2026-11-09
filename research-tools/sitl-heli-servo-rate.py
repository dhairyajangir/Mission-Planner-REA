"""Count SERVO_OUTPUT_RAW messages from a disposable ArduCopter-heli SITL in several situations, to see why the autotest RotorRunup step reports
"Did not get SERVO_OUTPUT_RAW after 1 second". Simulator only.

  A  after REQUEST_DATA_STREAM (all streams, 10 Hz) like the autotest harness does, disarmed
  B  same, after arming (force)
  C  after MAV_CMD_SET_MESSAGE_INTERVAL for message 36 at 10 Hz, armed
For each: messages seen in 5 s of wall clock, and the longest gap between two messages.

    python sitl-heli-servo-rate.py <ardupilot tree> <model, e.g. heli> <binary name, e.g. arducopter-heli> <out json>
"""
import json
import os
import subprocess
import sys
import time

from pymavlink import mavutil

tree, model, binary, out = sys.argv[1:5]
work = os.path.expanduser('~/heli-servo-rate')
subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
time.sleep(1)
os.makedirs(work, exist_ok=True)
proc = subprocess.Popen([os.path.join(tree, 'build/sitl/bin', binary), '-w', '--model', model, '-I', '0', '-s', '1', '--home', '-35.363261,149.165230,584,0'],
                        cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
result = {'model': model, 'binary': binary}
try:
    m = None
    t0 = time.time()
    while m is None and time.time() - t0 < 60:
        try:
            m = mavutil.mavlink_connection('tcp:127.0.0.1:5760', autoreconnect=False)
            m.wait_heartbeat(timeout=30)
        except Exception:
            m = None
            time.sleep(1)
    if m is None:
        result['status'] = 'no connection'
    else:
        def count(label, secs=5.0):
            end = time.time() + secs
            stamps = []
            while time.time() < end:
                msg = m.recv_match(type='SERVO_OUTPUT_RAW', blocking=True, timeout=0.2)
                if msg is not None:
                    stamps.append(time.time())
            gaps = [b - a for a, b in zip(stamps, stamps[1:])]
            result[label] = {'messages_in_%.0fs' % secs: len(stamps), 'longest_gap_s': round(max(gaps), 2) if gaps else None, 'first_after_s': round(stamps[0] - (end - secs), 2) if stamps else None}
            print(label, result[label], flush=True)

        time.sleep(15)                                                    # let the vehicle finish starting up
        m.mav.request_data_stream_send(m.target_system, 1, mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
        count('A_stream_request_disarmed')
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
        time.sleep(2)
        count('B_stream_request_armed')
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 100000, 0, 0, 0, 0, 0)
        count('C_message_interval_armed')
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 21196, 0, 0, 0, 0, 0)
        result['status'] = 'ok'
finally:
    proc.terminate()
    json.dump(result, open(out, 'w'), indent=1)
