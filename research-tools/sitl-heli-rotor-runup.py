"""Measure, on a disposable ArduCopter-heli SITL at speedup 1 (wall clock = simulator time), how long after the pilot raises the rotor-speed switch and throttle the
collective servo (SERVO_OUTPUT_RAW.servo1_raw) rises 50 microseconds above its armed value, with H_RSC_RUNUP_TIME = 10 s. This is the interval the autotest
RotorRunup step waits for with a wall-clock timeout of 1 second (assert_receive_message default). It does not run the autotest; it repeats its actions with pymavlink:
LOITER, normal (not forced) arming once the vehicle accepts it, then RC8 = 2000 (rotor interlock) and RC3 = 1700. A first version used STABILIZE with a forced arm;
there the collective followed the stick at once (0.16 s), which is a different path from the autotest's LOITER, so it was replaced and its result is kept in the trace.

    python sitl-heli-rotor-runup.py <ardupilot tree> <out json>
"""
import json
import os
import subprocess
import sys
import time

from pymavlink import mavutil

tree, out = sys.argv[1:3]
work = os.path.expanduser('~/heli-rotor-runup')
subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
time.sleep(1)
os.makedirs(work, exist_ok=True)
proc = subprocess.Popen([os.path.join(tree, 'build/sitl/bin/arducopter-heli'), '-w', '--model', 'heli', '-I', '0', '-s', '1', '--home', '-35.363261,149.165230,584,0'],
                        cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
result = {}
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
        raise SystemExit('no connection')
    time.sleep(10)
    m.mav.request_data_stream_send(m.target_system, 1, mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1)

    def setp(name, value):
        m.mav.param_set_send(m.target_system, m.target_component, name.encode(), value, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        time.sleep(0.5)

    def servo1(timeout=2):
        msg = m.recv_match(type='SERVO_OUTPUT_RAW', blocking=True, timeout=timeout)
        return None if msg is None else msg.servo1_raw

    def rc(ch3, ch8):
        vals = [65535] * 18
        vals[2], vals[7] = ch3, ch8
        m.mav.rc_channels_override_send(m.target_system, m.target_component, *vals)

    setp('H_RSC_RUNUP_TIME', 10)
    m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, 5, 0, 0, 0, 0, 0)    # LOITER (custom mode 5)
    time.sleep(1)
    rc(1000, 1000)
    armed = False
    t_arm = time.time()
    while not armed and time.time() - t_arm < 150:
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=3)
        armed = bool(hb is not None and hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    result['armed'] = armed
    result['seconds_to_arm'] = round(time.time() - t_arm, 1)
    time.sleep(1)
    base = servo1()
    result['servo1_armed_us'] = base
    t_start = time.time()
    crossed = None
    last = base
    while time.time() - t_start < 40:
        rc(1700, 2000)
        v = servo1(0.2)
        if v is not None:
            last = v
            if base is not None and v > base + 50 and crossed is None:
                crossed = time.time() - t_start
                break
    result['seconds_until_servo1_above_armed_plus_50'] = None if crossed is None else round(crossed, 2)
    result['last_servo1_us'] = last
    result['autotest_wait_limit_s'] = 1
    rc(1000, 1000)
    m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 21196, 0, 0, 0, 0, 0)
    print(result, flush=True)
finally:
    proc.terminate()
    json.dump(result, open(out, 'w'), indent=1)
