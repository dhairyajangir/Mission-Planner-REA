"""QuadPlane forward-transition failure (Q_TRANS_FAIL / Q_TRANS_FAIL_ACT) and Q_ASSIST_SPEED assistance, flown. Disposable ArduPlane SITL, model quadplane. Simulator only.

    python3 sitl-quadplane-vtol-failsafe.py <ardupilot tree> <out dir> <custom-gcs dir> <scenario> [scenario ...]

Source read first (ArduPlane/quadplane.cpp SLT_Transition::update, ArduPlane/VTOL_Assist.cpp should_assist, mode_qrtl.cpp):
  * the parameter names are Q_TRANS_FAIL (seconds, 0 = no limit) and Q_TRANS_FAIL_ACT (-1 warn only, 0 QLAND, 1 QRTL); there is no *_TIMEOUT / *_ACTION name.
  * the timer runs only in State::AIRSPEED_WAIT, from the "Transition started airspeed" text (transition_start_ms is zeroed by VTOL_update while in VTOL flight).
  * the forward transition ends when airspeed > AIRSPEED_MIN *and* the assist is not asking for help (airspeed >= Q_ASSIST_SPEED). quadplane.parm: AIRSPEED_MIN 13, Q_ASSIST_SPEED 18.
  * the speed assist has no delay (the Q_ASSIST_DELAY hysteresis is for the alt and angle triggers only). Once airspeed drops under Q_ASSIST_SPEED in a fixed-wing mode,
    SLT_Transition::update() puts the state machine back to AIRSPEED_WAIT (so the Q_TRANS_FAIL timer applies again) and holds the lift motors in hover assistance.
Scenarios:
    trans-control10, trans-3-qland, trans-3-qrtl, trans-3-warn   Q_TRANS_FAIL 10 (longer than a normal transition) or 3 (shorter) with Q_TRANS_FAIL_ACT 0 / 1 / -1.
    assist-18-slow, assist-off-slow, assist-18-slow-transfail8, assist-18-slow-transfail1, assist-18-slow-transfail1-late
                                                                  cruise in a loiter, then AIRSPEED_CRUISE lowered to 14 so the airspeed decays through Q_ASSIST_SPEED.
"""
import csv
import math
import os
import socket
import struct
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
WANTED = sys.argv[4:]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

INSTANCE = 4
MAV_PORT = 5760 + 10 * INSTANCE   # SITL_cmdline.cpp: -I n adds 10*n to the base port 5760 ...
RC_PORT = 5501 + 10 * INSTANCE    # ... and to the RC input port 5501
HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
WATCH_S = 100.0

# name -> (params set before arming, route kind, action after "Transition done", params set then, watch seconds)
SCENARIOS = {
    'trans-control10': ({'Q_TRANS_FAIL': 10, 'Q_TRANS_FAIL_ACT': 0}, 'land', None, {}, 70.0),
    'trans-3-qland': ({'Q_TRANS_FAIL': 3, 'Q_TRANS_FAIL_ACT': 0}, 'land', None, {}, 100.0),
    'trans-3-qrtl': ({'Q_TRANS_FAIL': 3, 'Q_TRANS_FAIL_ACT': 1}, 'land', None, {}, 100.0),
    'trans-3-warn': ({'Q_TRANS_FAIL': 3, 'Q_TRANS_FAIL_ACT': -1}, 'land', None, {}, 70.0),
    'assist-18-slow': ({}, 'loiter', 12.0, {'AIRSPEED_CRUISE': 14}, 70.0),
    'assist-off-slow': ({'Q_ASSIST_SPEED': -1}, 'loiter', 12.0, {'AIRSPEED_CRUISE': 14}, 70.0),
    'assist-18-slow-transfail8': ({'Q_TRANS_FAIL': 8, 'Q_TRANS_FAIL_ACT': 0}, 'loiter', 12.0, {'AIRSPEED_CRUISE': 14}, 90.0),
    # added after assist-18-slow showed each assisted AIRSPEED_WAIT lasts only 1.1-2.2 s (so a Q_TRANS_FAIL of 8 s cannot fire): 1 s is the smallest non-zero value
    'assist-18-slow-transfail1': ({'Q_TRANS_FAIL': 1, 'Q_TRANS_FAIL_ACT': 0}, 'loiter', 12.0, {'AIRSPEED_CRUISE': 14}, 90.0),
    # transfail1 fired on the very first forward transition, before the assist re-entry could be tested; here Q_TRANS_FAIL is set only with the slow-down, after "Transition done"
    'assist-18-slow-transfail1-late': ({}, 'loiter', 12.0, {'AIRSPEED_CRUISE': 14, 'Q_TRANS_FAIL': 1, 'Q_TRANS_FAIL_ACT': 0}, 90.0),
}
WATCH_PARAMS = ['Q_ENABLE', 'Q_ASSIST_SPEED', 'Q_ASSIST_ANGLE', 'Q_ASSIST_ALT', 'Q_ASSIST_DELAY', 'Q_ASSIST_OPTIONS', 'Q_TRANS_FAIL', 'Q_TRANS_FAIL_ACT', 'Q_OPTIONS', 'Q_RTL_MODE',
                'Q_RTL_ALT', 'AIRSPEED_MIN', 'AIRSPEED_MAX', 'AIRSPEED_CRUISE', 'ARSPD_USE', 'FS_GCS_ENABL', 'Q_FRAME_CLASS', 'SERVO5_FUNCTION', 'SERVO6_FUNCTION',
                'SERVO7_FUNCTION', 'SERVO8_FUNCTION']


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def route(kind):
    a, b = at(250, 0), at(250, 250)
    items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 84, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 30.0),
             mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, a[0], a[1], 60.0)]
    if kind == 'land':   # the route run_quadplane_failsafes.py flies: second waypoint, then a VTOL landing at home
        items += [mission.Item(3, 3, 16, 0, 1, 0, 0, 0, 0, b[0], b[1], 60.0), mission.Item(4, 3, 85, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], 0.0)]
    else:                # NAV_LOITER_UNLIM (17) at the second point: cruise in circles until the experiment ends
        items += [mission.Item(3, 3, 17, 0, 1, 0, 0, 0, 0, b[0], b[1], 60.0)]
    return items


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in WANTED:
        run(name, *SCENARIOS[name])


def run(name, pre, kind, slow_after_done_s, slow_params, watch_s):
    work = os.path.expanduser('~/cg-swarm-4-quadplane-vtol-failsafe/' + name)
    subprocess.call(['rm', '-rf', work])   # own directory only; never a name-based kill (other workers' simulators run at the same time)
    os.makedirs(work)
    notes, track, state = [], [], {'asp': None, 'gs': None, 'alt': None, 'thr': None, 'rel': None, 'n': None, 'e': None, 's': [None] * 4, 'mode': None, 'armed': None}
    beat = {'on': True}
    proc = subprocess.Popen([BIN, '-w', '--model', 'quadplane', '-I', str(INSTANCE), '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(MAV_PORT, timeout=120.0)
        conn.mav.heartbeat_send(6, 8, 0, 0, 0)

        def beats():
            while beat['on']:
                try:
                    conn.mav.heartbeat_send(6, 8, 0, 0, 0)
                except Exception:
                    return
                time.sleep(1.0)
        threading.Thread(target=beats, daemon=True).start()
        time.sleep(55)
        base = link.read_params(conn)
        notes.append('scenario %s: pre %s route %s slow-after-done %s slow-params %s' % (name, pre, kind, slow_after_done_s, slow_params))
        notes.append('defaults read: %s' % {p: base.get(p) for p in WATCH_PARAMS})
        bad = [r.name for r in params.write(conn, [params.Change(k, base.get(k), float(v)) for k, v in pre.items()]) if not r.ok]
        notes.append('pre-flight params set %s (rejected %s)' % (pre, bad))
        if pre:
            rd = link.read_params(conn, quiet_seconds=4.0)
            notes.append('read back: %s' % {k: rd.get(k) for k in pre})
        for msgid, us in ((74, 200000), (36, 200000), (33, 200000)):   # VFR_HUD, SERVO_OUTPUT_RAW, GLOBAL_POSITION_INT
            conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, msgid, us, 0, 0, 0, 0, 0)
        notes.append('upload ack %s' % mission.upload(conn, route(kind)))
        flight.set_mode(conn, 'MANUAL', table='plane')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if not armed.ok:
            return
        auto = flight.set_mode(conn, 'AUTO', table='plane')
        give_up = time.time() + 90.0
        while not auto.ok and time.time() < give_up:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table='plane')
        notes.append('AUTO: %s' % auto.detail)
        begin, last_mode, done_at, slowed_at, last_row = time.time(), None, None, None, 0.0
        while time.time() - begin < watch_s:
            msg = conn.recv_match(blocking=True, timeout=1)
            t = time.time() - begin
            if msg is not None:
                kind_ = msg.get_type()
                if kind_ == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                    if msg.text.startswith('Transition done') and done_at is None:
                        done_at = t
                elif kind_ == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    state['mode'], state['armed'] = flight.mode_name(msg.custom_mode, 'plane'), flight.is_armed(msg)
                    if state['mode'] != last_mode:
                        notes.append('t=%5.1f mode %s armed=%s' % (t, state['mode'], state['armed']))
                        last_mode = state['mode']
                    if not state['armed'] and t > 20:
                        notes.append('t=%5.1f disarmed, stopping watch' % t)
                        break
                elif kind_ == 'VFR_HUD':
                    state.update(asp=msg.airspeed, gs=msg.groundspeed, alt=msg.alt, thr=msg.throttle)
                    if t - last_row >= 0.2:
                        track.append([round(t, 1), state['mode'], state['armed'], round(msg.airspeed, 1), round(msg.groundspeed, 1), round(msg.alt, 1), msg.throttle, state['rel'],
                                      state['n'], state['e']] + state['s'])
                        last_row = t
                elif kind_ == 'GLOBAL_POSITION_INT':
                    state.update(rel=round(msg.relative_alt / 1000.0, 1), n=round((msg.lat / 1e7 - HOME[0]) * M_LAT, 1), e=round((msg.lon / 1e7 - HOME[1]) * M_LON, 1))
                elif kind_ == 'SERVO_OUTPUT_RAW' and getattr(msg, 'port', 0) == 0:
                    state['s'] = [msg.servo5_raw, msg.servo6_raw, msg.servo7_raw, msg.servo8_raw]
            if slow_params and slowed_at is None and done_at is not None and t - done_at >= slow_after_done_s:
                bad = [r.name for r in params.write(conn, [params.Change(k, base.get(k), float(v)) for k, v in slow_params.items()]) if not r.ok]
                notes.append('t=%5.1f experiment change %s (rejected %s); airspeed then %s' % (time.time() - begin, slow_params, bad, state['asp']))
                slowed_at = time.time() - begin
        notes.append('end t=%.1f mode %s armed %s airspeed %s rel-alt %s' % (time.time() - begin, state['mode'], state['armed'], state['asp'], state['rel']))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        beat['on'] = False
        proc.terminate()
        try:
            proc.wait(30)
        except Exception:
            proc.kill()
        with open(os.path.join(OUT, name + '-notes.txt'), 'w') as f:
            f.write('\n'.join(notes) + '\n')
        with open(os.path.join(OUT, name + '-track.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['seconds', 'mode', 'armed', 'airspeed_ms', 'groundspeed_ms', 'alt_amsl_m', 'throttle_pct', 'rel_alt_m', 'north_m', 'east_m', 'servo5', 'servo6', 'servo7', 'servo8'])
            w.writerows(track)
        subprocess.call(['cp', os.path.join(work, 'sitl.log'), os.path.join(OUT, name + '-sitl.log')])
        print('[%s] done: %d track rows, %d note lines' % (name, len(track), len(notes)), flush=True)


if __name__ == '__main__':
    main()
