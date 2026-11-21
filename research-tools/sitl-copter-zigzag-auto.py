"""Copter ZIGZAG mode 'auto' feature (ZIGZ_AUTO_ENABLE, ZIGZAG_Auto aux switch, ZIGZ_LINE_NUM / SIDE_DIST / DIRECTION), flown. Simulator only (SITL instance 2, worker 2 of the swarm).

ArduPilot's own autotest ModeZigZag only flies the manual part (aux 61 SaveWP: low = store A, high = store B, then low/high again = fly to A/B); it never sets
ZIGZ_AUTO_ENABLE, never uses aux 83 (ZIGZAG_Auto) and never sets LINE_NUM, SIDE_DIST or DIRECTION.

Source read first (ArduCopter/mode_zigzag.cpp, RC_Channel_Copter.cpp):
 * run_auto() (aux 83 high): needs ZIGZ_AUTO_ENABLE and stage == MANUAL_REGAIN; it does NOT fly to A or B first, it calls move_to_side() (a SIDE_DIST leg to the 'DIRECTION' side), because
   is_suspended is false. 'moving to <forward|right|backward|left>'.
 * run(): on reaching a destination (wp_nav reached and within 3 m, then WP_DELAY s) in auto: SIDEWAYS leg done -> save_or_move_to_destination(other of ab_dest_stored) which prints
   'moving to A|B (line n/N)' and does line_count++ (the '(line n/N)' suffix only when LINE_NUM is not -1); AB leg done -> if line_num == -1 or line_count < line_num -> next sideways leg, else
   init_auto() + return_to_manual_control() -> 'manual control'.  So LINE_NUM=N flies N AB legs but N sideways legs (the first auto leg is a sideways one); LINE_NUM=0 flies a single sideways leg only.
 * ab_dest_stored is never initialised (the declaration has no initialiser), so which of A/B the first AB leg goes to is whatever the member happened to hold: reported, not predicted.
 * suspend (aux 83 not high): suspend_auto() -> is_suspended, return_to_manual_control(true) -> 'manual control'.  Resume (aux 83 high again): run_auto() resumes the interrupted leg only if
   'line_count <= line_num'; with LINE_NUM = -1 that is false for every line_count >= 0, so the else branch runs move_to_side() and the interrupted A/B leg is abandoned (hypothesis to test).
 * DIRECTION is relative to the heading at the time of the side leg, but the side vector is always perpendicular to AB: the sign picks which of the two perpendiculars.

SITL RC input is the UDP '<16H' socket (instance 2 -> port 5521), FLTMODE_CH=0, RC8_OPTION=61 (ZIGZAG_SaveWP), RC9_OPTION=83 (ZIGZAG_Auto), throttle centred (1500). ZIGZ_AUTO_ENABLE is an
AP_PARAM_FLAG_ENABLE parameter: set it, restart without -w, then the other ZIGZ_ parameters exist.

    python3 sitl-copter-zigzag-auto.py <ardupilot tree> <out dir> <custom-gcs dir> [case label ...]
"""
import csv
import json
import math
import os
import socket
import struct
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402
from pymavlink import mavutil  # noqa: E402

INSTANCE = 2
TCP_PORT = 5760 + 10 * INSTANCE
RC_PORT = 5501 + 10 * INSTANCE
HOME = (-35.363261, 149.165230, 584.0)
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
ALT_M = 20.0
MODES = {'STABILIZE': 0, 'ALT_HOLD': 2, 'GUIDED': 4, 'LOITER': 5, 'ZIGZAG': 24}
NAMES = {v: k for k, v in MODES.items()}
# label, ab axis ('east' = roll stick, 'north' = pitch stick), ZIGZ_DIRECTION, ZIGZ_LINE_NUM, ZIGZ_SIDE_DIST, suspend plan
CASES = [
    ('ab-east-forward-3lines', 'east', 0, 3, 8.0, None),
    ('ab-east-backward-1line', 'east', 2, 1, 6.0, None),
    ('ab-north-right-2lines', 'north', 1, 2, 6.0, None),
    ('ab-north-left-1line', 'north', 3, 1, 6.0, None),
    ('ab-east-forward-0lines', 'east', 0, 0, 6.0, None),
    ('ab-east-forward-3lines-suspend-resume', 'east', 0, 3, 8.0, 'finite'),
    ('ab-east-forward-infinite-suspend-resume', 'east', 0, -1, 6.0, 'infinite'),
    # added after the first full run: the same case again, so the first AB leg is the long one (ab_dest_stored persists between entries)
    ('ab-east-forward-infinite-suspend-resume-repeat', 'east', 0, -1, 6.0, 'infinite'),
]


class Rig:
    def __init__(self, conn):
        self.c = conn
        self.rc = [1500] * 16
        self.rc[2] = 1000
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.t_rc = self.t_hb = 0.0
        self.t0 = time.time()
        self.notes, self.events, self.rows = [], [], []
        self.pos = None       # (north, east, down, vn, ve)
        self.yaw = None
        self.mode = None
        self.armed = False
        self.alt = None
        self.case = None

    def now(self):
        return time.time() - self.t0

    def note(self, s):
        self.notes.append('t=%6.1f %s' % (self.now(), s))

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if time.time() - self.t_rc >= 0.04:
                self.sock.sendto(struct.pack('<16H', *self.rc), ('127.0.0.1', RC_PORT))
                self.t_rc = time.time()
            if time.time() - self.t_hb >= 1.0:
                self.c.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                self.t_hb = time.time()
            msg = self.c.recv_match(blocking=True, timeout=0.02)
            if msg is None:
                continue
            k = msg.get_type()
            if k == 'STATUSTEXT':
                self.note('vehicle: %s' % msg.text)
                self.events.append((self.now(), 'text', msg.text, self.pos, self.case))
            elif k == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                m = msg.custom_mode
                if m != self.mode:
                    self.note('mode=%s armed=%s' % (NAMES.get(m, m), flight.is_armed(msg)))
                self.mode, self.armed = m, flight.is_armed(msg)
            elif k == 'GLOBAL_POSITION_INT':
                self.alt = msg.relative_alt / 1000.0
            elif k == 'ATTITUDE':
                self.yaw = math.degrees(msg.yaw)
            elif k == 'LOCAL_POSITION_NED':
                self.pos = (msg.x, msg.y, msg.z, msg.vx, msg.vy)
                if self.case is not None:
                    self.rows.append([self.case, round(self.now(), 2), NAMES.get(self.mode, self.mode), round(msg.x, 2), round(msg.y, 2), round(-msg.z, 2),
                                      round(msg.vx, 2), round(msg.vy, 2), None if self.yaw is None else round(self.yaw, 1), self.rc[7], self.rc[8]])

    def set_mode(self, name, settle=1.0):
        self.c.mav.command_long_send(self.c.target_system, self.c.target_component, 176, 0, 1, MODES[name], 0, 0, 0, 0, 0)
        self.pump(settle)

    def texts_since(self, t):
        return [(round(e[0], 1), e[2]) for e in self.events if e[0] >= t and e[1] == 'text']

    def wait_text(self, needle, since, timeout):
        end = time.time() + timeout
        while time.time() < end:
            self.pump(0.1)
            for e in self.events:
                if e[0] >= since and e[1] == 'text' and needle in e[2]:
                    return e
        return None


def stream(conn):
    for mid, us in ((30, 20000), (32, 100000), (33, 100000), (65, 200000), (0, 100000)):
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, mid, us, 0, 0, 0, 0, 0)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def settle_still(r, limit=15.0):
    t = time.time()
    still_since = None
    while time.time() - t < limit:
        r.pump(0.1)
        if r.pos and math.hypot(r.pos[3], r.pos[4]) < 0.3:
            still_since = still_since or time.time()
            if time.time() - still_since > 1.0:
                return True
        else:
            still_since = None
    return False


def run_case(r, label, axis, direction, line_num, side_dist, suspend):
    wr = params.write(r.c, [params.Change('ZIGZ_DIRECTION', None, float(direction)), params.Change('ZIGZ_LINE_NUM', None, float(line_num)),
                            params.Change('ZIGZ_SIDE_DIST', None, side_dist), params.Change('ZIGZ_WP_DELAY', None, 0.0)])
    r.note('%s: params %s' % (label, [(w.name, w.got, w.ok) for w in wr]))
    r.rc[2], r.rc[7], r.rc[8] = 1500, 1500, 1500
    r.rc[0] = r.rc[1] = 1500
    r.set_mode('LOITER', 1.0)
    r.pump(4.0)
    r.case = label
    r.set_mode('ZIGZAG', 1.0)
    r.note('%s: mode=%s alt=%s yaw=%s' % (label, NAMES.get(r.mode, r.mode), r.alt, r.yaw))
    t_a = r.now()
    r.rc[7] = 1100
    ev = r.wait_text('point A stored', t_a, 3.0)
    pos_a = r.pos
    r.note('%s: A text %s at pos %s' % (label, ev is not None, pos_a))
    if axis == 'east':
        r.rc[0] = 1700
    else:
        r.rc[1] = 1300
    t = time.time()
    while time.time() - t < 15 and dist(r.pos, pos_a) < 15.0:
        r.pump(0.1)
    r.rc[0] = r.rc[1] = 1500
    still = settle_still(r)
    r.rc[7] = 1500
    r.pump(0.5)
    t_b = r.now()
    r.rc[7] = 1900
    evb = r.wait_text('point B stored', t_b, 3.0)
    pos_b = r.pos
    r.note('%s: B text %s at pos %s, AB length %.1f m, still=%s' % (label, evb is not None, pos_b, dist(pos_a, pos_b), still))
    r.rc[7] = 1500
    r.pump(1.0)
    t_auto = r.now()
    pos_auto = r.pos
    r.rc[8] = 1900      # ZIGZAG_Auto high -> run_auto()
    result = {'case': label, 'axis': axis, 'direction': direction, 'line_num': line_num, 'side_dist': side_dist, 'pos_a': pos_a, 'pos_b': pos_b, 'pos_at_auto': pos_auto,
              'yaw_at_auto_deg': r.yaw, 'suspend_plan': suspend}
    if suspend is None:
        end = r.wait_text('manual control', t_auto, 70.0)
        result['finished'] = end is not None
    else:
        first_ab = None
        t = time.time()
        while time.time() - t < 40 and first_ab is None:
            r.pump(0.1)
            for e in r.events:
                if e[0] >= t_auto and e[1] == 'text' and (e[2].startswith('ZigZag: moving to A') or e[2].startswith('ZigZag: moving to B')):
                    first_ab = e
                    break
        result['first_ab_text'] = None if first_ab is None else first_ab[2]
        if first_ab is not None:
            r.pump(1.5)
            t_susp = r.now()
            pos_susp = r.pos
            r.rc[8] = 1500
            r.pump(6.0)
            result['suspend'] = {'t': round(t_susp, 1), 'pos_at_suspend': pos_susp, 'pos_after_6s': r.pos, 'texts': r.texts_since(t_susp)}
            t_res = r.now()
            r.rc[8] = 1900
            if suspend == 'finite':
                end = r.wait_text('manual control', t_res + 0.5, 70.0)
                result['finished'] = end is not None
            else:
                r.pump(25.0)
                t_susp2 = r.now()
                r.rc[8] = 1500
                r.pump(5.0)
                result['finished'] = False
                result['second_suspend_t'] = round(t_susp2, 1)
            result['resume'] = {'t': round(t_res, 1), 'texts': r.texts_since(t_res)}
    r.rc[8] = 1500
    r.pump(3.0)
    result['texts'] = r.texts_since(t_auto)
    result['pos_end'] = r.pos
    r.note('RESULT ' + json.dumps(result))
    r.case = None
    r.rc[7] = r.rc[8] = 1500
    r.set_mode('LOITER', 1.0)
    r.pump(3.0)
    return result


def start(work, wipe):
    args = [BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', str(INSTANCE), '-s', '1', '--home', '%s,%s,%s,0' % HOME]
    return subprocess.Popen(args, cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def stop(proc):
    proc.terminate()
    try:
        proc.wait(60)
    except Exception:  # noqa: BLE001
        proc.kill()


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[4:]
    work = os.path.expanduser('~/cg-swarm-2-zigzag')
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = start(work, True)
    summaries, r = [], None
    try:
        conn, _ = link.connect(TCP_PORT, timeout=120.0)
        r = Rig(conn)
        r.note('connected tcp %d, RC udp %d' % (TCP_PORT, RC_PORT))
        r.pump(15)
        stream(conn)
        base = link.read_params(conn)
        r.note('before enable: ZIGZ_AUTO_ENABLE=%s ZIGZ_SIDE_DIST=%s ZIGZ_LINE_NUM=%s FLTMODE_CH=%s WPNAV_SPEED=%s' % (base.get('ZIGZ_AUTO_ENABLE'), base.get('ZIGZ_SIDE_DIST'), base.get('ZIGZ_LINE_NUM'), base.get('FLTMODE_CH'), base.get('WPNAV_SPEED')))
        wr = params.write(conn, [params.Change('FLTMODE_CH', base.get('FLTMODE_CH'), 0.0), params.Change('RC8_OPTION', base.get('RC8_OPTION'), 61.0),
                                 params.Change('RC9_OPTION', base.get('RC9_OPTION'), 83.0), params.Change('LOIT_OPTIONS', base.get('LOIT_OPTIONS'), 0.0),
                                 params.Change('ZIGZ_AUTO_ENABLE', base.get('ZIGZ_AUTO_ENABLE'), 1.0)])
        r.note('stage-1 params %s' % [(w.name, w.got, w.ok) for w in wr])
        r.pump(2)
        conn.close()
        stop(proc)
        proc = start(work, False)
        conn, _ = link.connect(TCP_PORT, timeout=120.0)
        r = Rig_replace(r, conn)
        r.pump(15)
        stream(conn)
        after = link.read_params(conn)
        r.note('after restart: ZIGZ_AUTO_ENABLE=%s ZIGZ_SIDE_DIST=%s ZIGZ_LINE_NUM=%s ZIGZ_DIRECTION=%s ZIGZ_WP_DELAY=%s ZIGZ_SPRAYER=%s FLTMODE_CH=%s RC8_OPTION=%s RC9_OPTION=%s' % (
            after.get('ZIGZ_AUTO_ENABLE'), after.get('ZIGZ_SIDE_DIST'), after.get('ZIGZ_LINE_NUM'), after.get('ZIGZ_DIRECTION'), after.get('ZIGZ_WP_DELAY'),
            after.get('ZIGZ_SPRAYER'), after.get('FLTMODE_CH'), after.get('RC8_OPTION'), after.get('RC9_OPTION')))
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        r.note('arm: %s' % armed.detail)
        if not armed.ok:
            return 1
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
        t = time.time()
        while time.time() - t < 60 and (r.alt is None or r.alt < ALT_M - 1.5):
            r.pump(0.3)
        r.note('takeoff alt=%s' % r.alt)
        r.rc[2] = 1500
        r.pump(5)
        for label, axis, d, n, s, sus in CASES:
            if only and label not in only:
                continue
            if not r.armed or r.alt is None or r.alt < 8:
                r.note('skipping %s: armed=%s alt=%s' % (label, r.armed, r.alt))
                continue
            summaries.append(run_case(r, label, axis, d, n, s, sus))
    except Exception as e:  # noqa: BLE001
        if r is not None:
            r.note('EXCEPTION %r' % (e,))
    finally:
        stop(proc)
        if r is not None:
            with open(os.path.join(OUT, 'zigzag-notes.txt'), 'w') as f:
                f.write('\n'.join(r.notes) + '\n')
            with open(os.path.join(OUT, 'zigzag-track.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['case', 'seconds', 'mode', 'north_m', 'east_m', 'rel_alt_m', 'vn_ms', 've_ms', 'yaw_deg', 'rc8', 'rc9'])
                w.writerows(r.rows)
            with open(os.path.join(OUT, 'zigzag-summary.json'), 'w') as f:
                json.dump(summaries, f, indent=1)
    return 0


def Rig_replace(old, conn):
    """New connection after the restart; keep the notes/events/rows and clock so the log is one timeline."""
    new = Rig(conn)
    new.t0, new.notes, new.events, new.rows = old.t0, old.notes, old.events, old.rows
    return new


if __name__ == '__main__':
    sys.exit(main())
