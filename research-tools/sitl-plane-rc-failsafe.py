"""ArduPlane RC (throttle) failsafe, flown: short -> long escalation, FS_SHORT_ACTN / FS_LONG_ACTN, THR_FS_VALUE, and what happens when RC returns. Simulator only.

Source read first (ArduPlane): radio.cpp control_failsafe / rc_throttle_value_ok / rc_failsafe_active (the rc_failsafe flag needs 10 consecutive 50 Hz bad frames),
system.cpp check_short_rc_failsafe / check_long_failsafe, events.cpp rc_failsafe_short_on_event / failsafe_long_on_event / rc_failsafe_short_off_event /
failsafe_long_off_event. Questions this answers by flying: (1) with FS_SHORT_ACTN=2 (FBWA glide) and FS_LONG_ACTN=0 (documented as "continue in the auto mode"),
which mode does the long failsafe leave the aircraft in, because the long handler looks at the CURRENT mode (FBWA after the short action), not the mode the failsafe
started in; (2) does the saved mode come back when RC returns during the short phase and after the long phase; (3) the THR_FS_VALUE trigger (valid pulses, throttle at or
below the threshold) versus the no-pulses trigger.

    python3 sitl-plane-rc-failsafe.py <ardupilot tree> <out dir> <custom-gcs dir> <worker K> [case label ...]

SITL runs with -I K: MAVLink TCP 5760+10K, RC UDP input 5501+10K. Only the Popen handle started here is terminated (no name-based kill).
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

TREE, OUT, GCS, K = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
PORT = 5760 + 10 * K
RC_UDP_PORT = 5501 + 10 * K
TABLE = 'plane'
CRUISE_ALT_M = 60.0
STEADY_PRE_S = 10.0     # settle time at cruise before the fault
# label: dict(pre=params set before arming, mode=mode the fault starts in, feed=UDP RC feeder on, inject=params set at t0, clear=params set at clear_at, clear_at/watch seconds)
CASES = {
    # finding 1: short FBWA action, long action "continue"
    'auto-fbwa-short-long-continue': dict(
        pre={'FS_SHORT_ACTN': 2, 'FS_LONG_ACTN': 0, 'FS_LONG_TIMEOUT': 5}, mode='AUTO', feed=False,
        inject={'SIM_RC_FAIL': 1}, clear={'SIM_RC_FAIL': 0}, clear_at=25.0, watch=45.0),
    'auto-fbwa-short-recover': dict(
        pre={'FS_SHORT_ACTN': 2, 'FS_LONG_ACTN': 1, 'FS_LONG_TIMEOUT': 30}, mode='AUTO', feed=False,
        inject={'SIM_RC_FAIL': 1}, clear={'SIM_RC_FAIL': 0}, clear_at=8.0, watch=30.0),
    # finding 2: throttle trigger, defaults and THR_FS_VALUE
    'auto-defaults-throttle950': dict(
        pre={}, mode='AUTO', feed=True,
        inject={'SIM_RC_FAIL': 2}, clear={'SIM_RC_FAIL': 0}, clear_at=14.0, watch=35.0),
    'fbwa-thrfsvalue-short-recover': dict(
        pre={}, mode='FLY_BY_WIRE_A', feed=True,
        inject={'THR_FS_VALUE': 1600}, clear={'THR_FS_VALUE': 950}, clear_at=3.0, watch=25.0),
    'fbwa-thrfsvalue-long': dict(
        pre={}, mode='FLY_BY_WIRE_A', feed=True,
        inject={'THR_FS_VALUE': 1600}, clear={'THR_FS_VALUE': 950}, clear_at=14.0, watch=40.0),
}


def route():
    a = (HOME[0] + 400.0 / M_LAT, HOME[1])
    b = (a[0], a[1] + 400.0 / M_LON)
    c = (HOME[0], a[1])
    return [mission.Item(0, 0, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, HOME[0], HOME[1], HOME[2]),
            mission.Item(1, 3, 22, 1, 1, 15.0, 0.0, 0.0, 0.0, 0.0, 0.0, CRUISE_ALT_M),
            mission.Item(2, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, a[0], a[1], CRUISE_ALT_M),
            mission.Item(3, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, b[0], b[1], CRUISE_ALT_M),
            mission.Item(4, 3, 17, 0, 1, 0.0, 0.0, 0.0, 0.0, c[0], c[1], CRUISE_ALT_M)]


class Flight:
    """Collects every message of interest with wall-clock stamps; times are made relative to the fault afterwards."""

    def __init__(self, conn):
        self.conn = conn
        self.events = []      # (wall, text)
        self.track = []       # (wall, lat, lon, alt, gs, airspeed, servo3, rc3, mode)
        self.state = dict(servo3=None, rc3=None, mode=None, airspeed=None, gs=None, seq=None, armed=None)
        self.last_alt = None

    def note(self, text):
        self.events.append((time.time(), text))

    def pump(self, seconds, stop=None):
        end = time.time() + seconds
        while time.time() < end:
            msg = self.conn.recv_match(blocking=True, timeout=0.3)
            if msg is None:
                continue
            kind = msg.get_type()
            now = time.time()
            if kind == 'STATUSTEXT':
                self.note('vehicle: %s' % msg.text)
            elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                mode = flight.mode_name(msg.custom_mode, TABLE)
                armed = flight.is_armed(msg)
                if mode != self.state['mode'] or armed != self.state['armed']:
                    self.note('HEARTBEAT mode=%s armed=%s' % (mode, armed))
                self.state['mode'], self.state['armed'] = mode, armed
            elif kind == 'SERVO_OUTPUT_RAW':
                self.state['servo3'] = msg.servo3_raw
            elif kind == 'RC_CHANNELS':
                self.state['rc3'] = msg.chan3_raw
            elif kind == 'VFR_HUD':
                self.state['airspeed'], self.state['gs'] = round(msg.airspeed, 1), round(msg.groundspeed, 1)
            elif kind == 'MISSION_CURRENT':
                if msg.seq != self.state['seq']:
                    self.note('MISSION_CURRENT seq=%s' % msg.seq)
                self.state['seq'] = msg.seq
            elif kind == 'PARAM_VALUE':
                self.note('PARAM_VALUE %s=%s' % (msg.param_id.rstrip('\x00'), msg.param_value))
            elif kind == 'GLOBAL_POSITION_INT':
                self.last_alt = msg.relative_alt / 1000.0
                s = self.state
                self.track.append((now, msg.lat / 1e7, msg.lon / 1e7, round(self.last_alt, 1), s['gs'], s['airspeed'], s['servo3'], s['rc3'], s['mode']))
            if stop is not None and stop():
                return True
        return False

    def set_param(self, name, value):
        self.conn.mav.param_set_send(self.conn.target_system, self.conn.target_component, name.encode(), float(value), 9)
        self.note('SENT param_set %s=%s' % (name, value))


def start_feeder(stop_flag):
    """Continuous SITL RC input: roll/pitch/yaw centred, throttle centred; channels 5-16 sent as 0 (= leave the SITL default)."""
    pkt = struct.pack('<16H', *([1500, 1500, 1500, 1500] + [0] * 12))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def run():
        while not stop_flag['stop']:
            sock.sendto(pkt, ('127.0.0.1', RC_UDP_PORT))
            time.sleep(0.1)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def run_case(label, spec):
    work = os.path.expanduser('~/cg-swarm-%d-plane-rc-%s' % (K, label))
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    header = ['case %s: pre=%s mode_at_fault=%s feed_udp_rc=%s inject=%s clear=%s clear_at=%.0fs watch=%.0fs; SITL -I %d (TCP %d, RC UDP %d)' % (
        label, spec['pre'], spec['mode'], spec['feed'], spec['inject'], spec['clear'], spec['clear_at'], spec['watch'], K, PORT, RC_UDP_PORT)]
    proc = subprocess.Popen([BIN, '-w', '--model', 'plane', '-I', str(K), '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    fl, t0 = None, None
    feeder = {'stop': False}
    try:
        conn, _ = link.connect(PORT, timeout=120.0)
        fl = Flight(conn)
        time.sleep(30)
        for msgid, us in ((33, 200000), (74, 500000), (65, 500000), (36, 500000), (42, 500000)):
            conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, msgid, us, 0, 0, 0, 0, 0)
        base = link.read_params(conn)
        header.append('defaults: THR_FAILSAFE=%s THR_FS_VALUE=%s FS_SHORT_ACTN=%s FS_LONG_ACTN=%s FS_LONG_TIMEOUT=%s RC_FS_TIMEOUT=%s FLTMODE_CH=%s SIM_RC_FAIL=%s FS_GCS_ENABL=%s' % tuple(
            base.get(n) for n in ('THR_FAILSAFE', 'THR_FS_VALUE', 'FS_SHORT_ACTN', 'FS_LONG_ACTN', 'FS_LONG_TIMEOUT', 'RC_FS_TIMEOUT', 'FLTMODE_CH', 'SIM_RC_FAIL', 'FS_GCS_ENABL')))
        changes = [params.Change('FLTMODE_CH', base.get('FLTMODE_CH'), 0.0)]
        changes += [params.Change(n, base.get(n), float(v)) for n, v in spec['pre'].items()]
        bad = [r.name for r in params.write(conn, changes) if not r.ok]
        header.append('pre-flight params set: FLTMODE_CH=0 plus %s (rejected %s)' % (spec['pre'], bad))
        header.append('mission upload ack %s' % mission.upload(conn, route()))
        flight.set_mode(conn, 'MANUAL', table=TABLE)
        armed = flight.arm(conn, timeout=150.0)
        header.append('arm: %s' % armed.detail)
        auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        retry = time.time() + 60.0
        while not auto.ok and time.time() < retry:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        header.append('AUTO: %s' % auto.detail)
        reached = fl.pump(90.0, stop=lambda: fl.last_alt is not None and fl.last_alt >= CRUISE_ALT_M - 5.0)
        header.append('reached cruise altitude: %s (alt %s)' % (reached, fl.last_alt))
        fl.pump(STEADY_PRE_S)
        if spec['feed']:
            start_feeder(feeder)      # started only now: in MANUAL on the runway a centred throttle would start a take-off roll; AUTO ignores the pilot throttle
            header.append('UDP RC feeder running (throttle centred 1500) from cruise, before the fault')
            fl.pump(3.0)
        if spec['mode'] != 'AUTO':
            res = flight.set_mode(conn, spec['mode'], table=TABLE)
            header.append('requested %s: %s' % (spec['mode'], res.detail))
            fl.pump(8.0)
        header.append('state before fault: mode=%s alt=%s servo3=%s rc3=%s' % (fl.state['mode'], fl.last_alt, fl.state['servo3'], fl.state['rc3']))
        t0 = time.time()
        for n, v in spec['inject'].items():
            fl.set_param(n, v)
        fl.pump(spec['clear_at'])
        for n, v in spec['clear'].items():
            fl.set_param(n, v)
        fl.pump(spec['watch'] - spec['clear_at'])
    except Exception as e:
        header.append('EXCEPTION %r' % (e,))
    finally:
        feeder['stop'] = True
        proc.terminate()
        try:
            proc.wait(60)
        except Exception:
            proc.kill()
    return header, fl, t0


def dump_onboard(label, spec):
    """Onboard DataFlash log (SITL's logs/*.BIN): MODE, MSG and the PARM records of the injected/cleared parameters, on the vehicle's own clock, relative to the injection.
    The wall-clock times in the MAVLink notes are not the vehicle's clock: with several simulators sharing the machine SITL ran slower than real time (see the trace)."""
    import glob
    from pymavlink import mavutil
    work = os.path.expanduser('~/cg-swarm-%d-plane-rc-%s' % (K, label))
    bins = sorted(glob.glob(os.path.join(work, 'logs', '*.BIN')))
    if not bins:
        return
    keys = set(spec['inject']) | set(spec['clear'])
    rows, ref = [], None
    m = mavutil.mavlink_connection(bins[-1])
    while True:
        x = m.recv_match(type=['MODE', 'MSG', 'PARM'], blocking=False)
        if x is None:
            break
        t = x.TimeUS / 1e6
        if x.get_type() == 'PARM':
            if x.Name not in keys:
                continue
            if ref is None and x.Name in spec['inject'] and abs(x.Value - spec['inject'][x.Name]) < 1e-6 and t > 40:
                ref = t
        rows.append((t, x))
    with open(os.path.join(OUT, label + '-onboard-log.txt'), 'w') as f:
        f.write('# %s: vehicle clock, seconds relative to the first injected PARM record (reference %s s of log time)\n' % (os.path.basename(bins[-1]), ref))
        for t, x in rows:
            if ref is None or t < ref - 25:
                continue
            kind = x.get_type()
            if kind == 'MODE':
                f.write('t=%7.2f MODE ModeNum=%d Rsn=%d\n' % (t - ref, x.ModeNum, x.Rsn))
            elif kind == 'MSG':
                f.write('t=%7.2f MSG %s\n' % (t - ref, x.Message))
            else:
                f.write('t=%7.2f PARM %s=%s\n' % (t - ref, x.Name, x.Value))


def write_out(label, header, fl, t0):
    notes = list(header)
    if fl is not None and t0 is not None:
        for wall, text in fl.events:
            notes.append('t=%6.1f %s' % (wall - t0, text))
    with open(os.path.join(OUT, label + '-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    if fl is not None and t0 is not None:
        with open(os.path.join(OUT, label + '-track.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['seconds_from_fault', 'lat', 'lon', 'relative_alt_m', 'groundspeed', 'airspeed', 'servo3_raw', 'rc3_raw', 'mode'])
            for row in fl.track:
                w.writerow([round(row[0] - t0, 1)] + list(row[1:]))
    print('[plane-rc-failsafe] %s done: %d events' % (label, len(fl.events) if fl else 0), flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[5:]
    for label, spec in CASES.items():
        if only and label not in only:
            continue
        header, fl, t0 = run_case(label, spec)
        write_out(label, header, fl, t0)
        try:
            dump_onboard(label, spec)
        except Exception as e:
            print('[plane-rc-failsafe] onboard log dump failed: %r' % (e,), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
