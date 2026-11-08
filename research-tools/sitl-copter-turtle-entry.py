"""Turtle mode entry gates against a disposable ArduCopter SITL (WSL, pymavlink). Never use with a real vehicle or live link.

ArduCopter/mode_turtle.cpp only starts Turtle mode when a DShot ESC type is configured (SERVO_DSHOT_ESC), the vehicle is disarmed,
the motor-control checks pass (landed, RC calibrated) and the pilot sticks are neutral. This test requests TURTLE (mode 28) in
steps and records the reported mode and the vehicle's own STATUSTEXT messages after each step:
  1. defaults, no RC input
  2. centred RC_CHANNELS_OVERRIDE on channels 1-4 only (no DShot type)
  3. SERVO_DSHOT_ESC = 1 (BLHeli DShot) with the RC override stopped
  4. SERVO_DSHOT_ESC = 1 with centred RC override
It does not test flipping a vehicle over: arming in Turtle mode uses a separate path and a crashed airframe, which is not simulated.

    python sitl-copter-turtle-entry.py <arducopter binary> <outdir>
"""
import csv
import json
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TURTLE = 28


class Link:
    def __init__(self, m):
        self.m = m
        self.hb = None
        self.texts = []
        self.rc = False

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if self.rc:
                self.m.mav.rc_channels_override_send(self.m.target_system, self.m.target_component, 1500, 1500, 1500, 1500, 0, 0, 0, 0)
            msg = self.m.recv_match(blocking=True, timeout=0.1)
            if msg is None:
                continue
            t = msg.get_type()
            if t == 'HEARTBEAT' and msg.autopilot == 3:
                self.hb = msg
            elif t == 'STATUSTEXT':
                self.texts.append(msg.text)

    def set_param(self, name, value):
        self.m.mav.param_set_send(self.m.target_system, self.m.target_component, name.encode(), float(value), mavutil.mavlink.MAV_PARAM_TYPE_INT8)
        self.pump(1.0)

    def try_turtle(self):
        self.texts.clear()
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, TURTLE, 0, 0, 0, 0, 0)
        ack = self.m.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        self.pump(2.0)
        return {'ack_result': None if ack is None else ack.result, 'custom_mode': None if self.hb is None else self.hb.custom_mode,
                'statustext': ' | '.join(self.texts)[:300]}


def main():
    binary, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    log = open(os.path.join(outdir, 'sitl.log'), 'w')
    proc = subprocess.Popen([binary, '-w', '-M', '+', '-I', '7', '-s', '5', '--home', '-35.363261,149.165230,584,0'], cwd=outdir, stdout=log, stderr=subprocess.STDOUT)
    rows = []
    try:
        m = None
        for _ in range(60):
            try:
                m = mavutil.mavlink_connection('tcp:127.0.0.1:5830', autoreconnect=False)
                break
            except Exception:
                time.sleep(0.5)
        m.wait_heartbeat(timeout=30)
        L = Link(m)
        m.mav.request_data_stream_send(m.target_system, m.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
        t0 = time.time()
        while time.time() - t0 < 120:
            L.pump(0.5)
            if any('using GPS' in t for t in L.texts):
                break
        L.pump(3)
        for step, action in (('1 defaults, no RC input', None),
                             ('2 centred RC override only (no DShot type)', 'rc_on'),
                             ('3 SERVO_DSHOT_ESC=1, RC override stopped', 'dshot_rc_off'),
                             ('4 SERVO_DSHOT_ESC=1, centred RC override', 'rc_on')):
            if action == 'rc_on':
                L.rc = True
                L.pump(1.0)
            elif action == 'dshot_rc_off':
                L.rc = False
                L.set_param('SERVO_DSHOT_ESC', 1)
                L.pump(5.0)       # let the override time out (RC_OVERRIDE_TIME)
            elif action:
                L.set_param(*action)
            r = L.try_turtle()
            r['step'] = step
            rows.append(r)
            print(r, flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()
    with open(os.path.join(outdir, 'turtle-entry.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, ['step', 'ack_result', 'custom_mode', 'statustext'], lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    json.dump(rows, open(os.path.join(outdir, 'turtle-entry.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
