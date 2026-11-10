"""The ArduPlane airframe variants of the simulator, each flown once with full DataFlash logging. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-plane-variants.py <ardupilot tree> <out dir> <custom-gcs dir> [variant ...]

Each variant is started as `arduplane -w --model <frame> --defaults <files>` with the default-parameter files that Tools/autotest/pysim/vehicleinfo.json lists for the frame (here from
the snapshot's own directories), plus a one-line file setting LOG_BITMASK 4194303. Two kinds of mission, as in the earlier flights:
  plane  automatic takeoff to 60 m, three waypoints, an automatic landing (sitl-aerial-evidence.py)
  vtol   VTOL takeoff to 30 m, two waypoints at 60 m, a VTOL landing (sitl-plane-gaps.py)
The vehicle is armed in MANUAL, put in AUTO (retried for 90 s) and followed until it disarms by itself or 300 s pass. The DataFlash .BIN is gzipped next to a JSON note with its size,
SHA-256, the frame parameters read back, the vehicle's texts with times and the STAT counters before and after. A variant that cannot be armed or flown is recorded as it happened.
TAILSITTER_REBOOT=1 restarts the simulator once (without wiping) when the frame has Q_TAILSIT_ENABLE 1, as ArduPilot's own FlyEachFrame test does ("tailsitter needs extra
re-boot to pick up the rotated AHRS view").
ICE_START_CH11=1 holds RC channel 11 at 1900 by RC override for the whole flight: the ICE frames' parameter file sets RC11_OPTION 179 (ICE start/stop), the engine starts with
the channel at or above 1700, and without it the plane never leaves the ground (plane-ice) or flies very slowly (quadplane-ice).
"""
import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-plane-variants')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
T = os.path.join(TREE, 'Tools/autotest')
P = os.path.join(T, 'models/plane.parm')
DP = lambda n: os.path.join(T, 'default_params', n)  # noqa: E731
QP = DP('quadplane.parm')
# frame -> (kind, [default files])
VARIANTS = {
    'plane': ('plane', [P]),
    'plane-elevon': ('plane', [P, DP('plane-elevons.parm')]),
    'plane-vtail': ('plane', [P, DP('plane-vtail.parm')]),
    'plane-jet': ('plane', [P, DP('plane-jet.parm')]),
    'plane-dspoilers': ('plane', [P, DP('plane-dspoilers.parm')]),
    'plane-ice': ('plane', [P, DP('plane-ice.parm')]),
    'plane-3d': ('plane', [P, os.path.join(T, 'models/plane-3d.parm')]),
    'quadplane-tri': ('vtol', [QP, DP('quadplane-tri.parm')]),
    'quadplane-tilt': ('vtol', [QP, DP('quadplane-tilt.parm')]),
    'quadplane-tilttri': ('vtol', [QP, DP('quadplane-tilttri.parm')]),
    'quadplane-tilttrivec': ('vtol', [QP, DP('quadplane-tilttrivec.parm')]),
    'quadplane-tilthvec': ('vtol', [P, DP('quadplane-tilthvec.parm')]),
    'quadplane-cl84': ('vtol', [QP, DP('quadplane-cl84.parm')]),
    'quadplane-ice': ('vtol', [QP, DP('plane-ice.parm'), DP('quadplane-ice.parm')]),
    'quadplane-copter_tailsitter': ('vtol', [QP, DP('quadplane-copter_tailsitter.parm')]),
    'plane-tailsitter': ('vtol', [DP('plane-tailsitter.parm')]),
    'firefly': ('vtol', [QP, DP('firefly.parm')]),
}
WANT = sys.argv[4:] or list(VARIANTS)
ICE_START = bool(os.environ.get('ICE_START_CH11'))
TAIL_REBOOT = bool(os.environ.get('TAILSITTER_REBOOT'))


class IceSwitch(threading.Thread):
    def __init__(self, conn):
        super().__init__(daemon=True)
        self.conn, self.running = conn, True

    def run(self):
        while self.running:
            try:
                self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1900, 0, 0, 0, 0, 0, 0, 0)
            except Exception:
                pass
            time.sleep(0.1)
KEEP = ('Q_ENABLE', 'Q_FRAME_CLASS', 'Q_FRAME_TYPE', 'Q_TILT_ENABLE', 'Q_TILT_TYPE', 'Q_TAILSIT_ENABLE', 'Q_OPTIONS', 'LOG_BITMASK', 'ICE_ENABLE', 'DSPOILER_OPTS', 'MIXING_GAIN', 'KFF_RDDRMIX')


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def item(seq, command, point=(0.0, 0.0), alt=0.0, p1=0.0):
    return mission.Item(seq, 3, command, 1 if seq == 1 else 0, 1, p1, 0, 0, 0, point[0], point[1], alt)


def home_item():
    return mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2])


def mission_for(kind):
    if kind == 'plane':
        return [home_item(), item(1, 22, alt=60.0, p1=15.0), item(2, 16, at(300, 0), 60.0), item(3, 16, at(300, 300), 60.0), item(4, 16, at(0, 300), 40.0), item(5, 21, (HOME[0], HOME[1]), 0.0)]
    return [home_item(), item(1, 84, alt=30.0), item(2, 16, at(250, 0), 60.0), item(3, 16, at(250, 250), 60.0), item(4, 85, (HOME[0], HOME[1]), 0.0)]


def stats(conn):
    p = link.read_params(conn)
    return {k: p[k] for k in sorted(p) if k.startswith('STAT_')}, p


def fly(name, kind, defaults):
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    work = os.path.join(WORK, name)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    extra = os.path.join(work, 'logall.parm')
    open(extra, 'w').write('LOG_BITMASK 4194303\n')
    missing = [d for d in defaults if not os.path.isfile(d)]
    result = {'variant': name, 'kind': kind, 'defaults': [os.path.relpath(d, TREE) for d in defaults], 'missing_default_files': missing}
    notes, proc = [], None
    if missing:
        notes.append('default files missing: %s' % missing)
    else:
        proc = subprocess.Popen([BIN, '-w', '--model', name, '--defaults', ','.join(defaults + [extra]), '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                                stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
        try:
            conn, mav_type = link.connect(5760, timeout=120.0)
            result['mav_type'] = mav_type
            time.sleep(50)
            result['stat_before'], p = stats(conn)
            switch = None
            if ICE_START:
                switch = IceSwitch(conn)
                switch.start()
                notes.append('RC channel 11 held at 1900 (ICE start)')
            result['params'] = {k: p.get(k) for k in KEEP}
            if TAIL_REBOOT and p.get('Q_TAILSIT_ENABLE'):
                notes.append('Q_TAILSIT_ENABLE is set: restarting the simulator once, without wiping')
                subprocess.call(['pkill', '-x', 'arduplane'])
                try:
                    proc.wait(15)
                except Exception:
                    proc.kill()
                time.sleep(2)
                proc = subprocess.Popen([BIN, '--model', name, '--defaults', ','.join(defaults + [extra]), '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                                        stdout=open(os.path.join(work, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
                conn, _ = link.connect(5760, timeout=120.0)
                time.sleep(50)
                result['stat_before'], p = stats(conn)
                result['params_after_reboot'] = {k: p.get(k) for k in KEEP}
            notes.append('upload ack %s' % mission.upload(conn, mission_for(kind)))
            flight.set_mode(conn, 'MANUAL', table='plane')
            armed = flight.arm(conn, timeout=150.0)
            notes.append('arm: %s' % armed.detail)
            if armed.ok:
                auto = flight.set_mode(conn, 'AUTO', table='plane')
                give_up = time.time() + 90.0
                while not auto.ok and time.time() < give_up:
                    time.sleep(3)
                    auto = flight.set_mode(conn, 'AUTO', table='plane')
                notes.append('AUTO: %s' % auto.detail)
                begin, was = time.time(), False
                while auto.ok and time.time() - begin < 300.0:
                    msg = conn.recv_match(type=['HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
                    if msg is None:
                        continue
                    t = time.time() - begin
                    if msg.get_type() == 'STATUSTEXT':
                        notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                    elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                        now = flight.is_armed(msg)
                        if was and not now:
                            notes.append('t=%5.1f disarmed' % t)
                            break
                        was = was or now
            else:
                notes.extend('vehicle: ' + t for t in armed.texts)
            time.sleep(5)
            result['stat_after'], _ = stats(conn)
        except Exception as e:
            notes.append('EXCEPTION %r' % (e,))
        finally:
            if 'switch' in dir() and switch is not None:
                switch.running = False
            subprocess.call(['pkill', '-x', 'arduplane'])
            try:
                proc.wait(15)
            except Exception:
                proc.kill()
    time.sleep(1)
    kept = []
    logs = os.path.join(work, 'logs')
    if os.path.isdir(logs):
        for f in sorted(os.listdir(logs)):
            if f.endswith('.BIN'):
                raw = open(os.path.join(logs, f), 'rb').read()
                target = os.path.join(OUT, '%s-logged-flight-%s.gz' % (name, f))
                with gzip.open(target, 'wb') as dst:
                    dst.write(raw)
                kept.append({'file': os.path.basename(target), 'raw_bytes': len(raw), 'gz_bytes': os.path.getsize(target), 'gz_sha256': hashlib.sha256(open(target, 'rb').read()).hexdigest()})
    result.update({'notes': notes, 'logs': kept})
    with open(os.path.join(OUT, '%s-logged-flight.json' % name), 'w') as f:
        json.dump(result, f, indent=1)
    flown = [n for n in notes if 'arm:' in n or 'disarmed' in n or 'EXCEPTION' in n or 'missing' in n]
    print('[%s] logs %d; %s' % (name, len(kept), flown[:3]), flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in WANT:
        kind, defaults = VARIANTS[name]
        fly(name, kind, defaults)
    return 0


if __name__ == '__main__':
    sys.exit(main())
