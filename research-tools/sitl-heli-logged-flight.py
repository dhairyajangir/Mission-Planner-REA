"""A logged flight of the helicopter build in a simulator, so the helicopter has airborne DataFlash samples like the Copter and Plane have. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-heli-logged-flight.py <ardupilot tree> <out dir> <custom-gcs dir>

LOG_BITMASK is set to log everything (4194303) on a first start, a second start (no wipe) keeps it. The motor-interlock RC switch (channel 8) is driven by RC override: low to arm, high to run the
rotor (see sitl-heli-flight.py). An AUTO mission (takeoff to 20 m, a waypoint 40 m north with a 30 s loiter, return to launch) is flown; the DataFlash .BIN is kept gzipped and its SHA-256 and
size are written to `heli-logged-flight.json` with the vehicle's texts and the STAT counters before and after.
"""
import gzip
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
WORK = os.path.expanduser('~/cg-heli-log')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter-heli')


def start(wipe):
    return subprocess.Popen([BIN] + (['-w'] if wipe else []) + ['--model', 'heli', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def stop(proc):
    proc.terminate()
    try:
        proc.wait(10)
    except Exception:
        proc.kill()


class Sticks(threading.Thread):
    def __init__(self, conn):
        super().__init__(daemon=True)
        self.conn, self.collective, self.interlock, self.running = conn, 1000, 1000, True

    def run(self):
        while self.running:
            try:
                self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component, 1500, 1500, self.collective, 1500, 0, 0, 0, self.interlock)
            except Exception:
                pass
            time.sleep(0.1)


def stats(conn):
    p = link.read_params(conn)
    return {k: p[k] for k in sorted(p) if k.startswith('STAT_')}


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter-heli'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, result, sticks, proc = [], {}, None, None
    try:
        proc = start(True)
        conn, _ = link.connect(5760)
        time.sleep(15)
        base = link.read_params(conn)
        bad = [r.name for r in params.write(conn, [params.Change('LOG_BITMASK', base.get('LOG_BITMASK'), 4194303.0)]) if not r.ok]
        notes.append('LOG_BITMASK was %s, set to 4194303 (rejected %s)' % (base.get('LOG_BITMASK'), bad))
        time.sleep(2)
        stop(proc)
        proc = start(False)
        conn, _ = link.connect(5760)
        time.sleep(45)
        result['stat_before'] = stats(conn)
        sticks = Sticks(conn)
        sticks.start()
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 20.0),
                 mission.Item(2, 3, 19, 0, 1, 30.0, 0, 0, 0, HOME[0] + 40 / M_LAT, HOME[1], 20.0), mission.Item(3, 3, 20, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        notes.append('STABILIZE: %s' % flight.set_mode(conn, 'STABILIZE').detail)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            sticks.interlock = 2000
            time.sleep(25)
            sticks.collective = 1500
            auto = flight.set_mode(conn, 'AUTO')
            notes.append('AUTO: %s' % auto.detail)
            notes.append('start: %s' % flight.start_mission(conn).detail)
            begin, last, was = time.time(), None, False
            while time.time() - begin < 240.0:
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
        time.sleep(5)
        result['stat_after'] = stats(conn)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        if proc:
            stop(proc)
    time.sleep(1)
    logs = os.path.join(WORK, 'logs')
    kept = []
    if os.path.isdir(logs):
        for f in sorted(os.listdir(logs)):
            if f.endswith('.BIN'):
                target = os.path.join(OUT, 'heli-logged-flight-%s.gz' % f)
                raw = open(os.path.join(logs, f), 'rb').read()
                with gzip.open(target, 'wb') as dst:
                    dst.write(raw)
                kept.append({'file': os.path.basename(target), 'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest(), 'gz_bytes': os.path.getsize(target)})
    result.update({'notes': notes, 'logs': kept})
    with open(os.path.join(OUT, 'heli-logged-flight.json'), 'w') as f:
        json.dump(result, f, indent=1)
    print('[heli-log] logs %s' % [k['file'] for k in kept], flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
