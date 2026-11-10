"""The helicopter frame variants of the simulator, each flown once with full DataFlash logging. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-heli-variants.py <ardupilot tree> <out dir> <custom-gcs dir> [variant ...]

Variants (from Tools/autotest/pysim/vehicleinfo.json: a model name and the default-parameter files it is started with, here passed with --defaults):
  heli-gas        copter-heli.parm + copter-heli-gas.parm
  heli-ddvptail   copter-heli.parm + copter-heli-ddvptail.parm  (direct-drive variable-pitch tail)
  heli-ddfptail   copter-heli.parm + copter-heli-ddfptail.parm  (direct-drive fixed-pitch tail)
  heli-dual       copter-heli.parm + copter-heli-dual.parm      (FRAME_CLASS 11, two main rotors)
  heli-blade360   copter-heli.parm only, a different simulator model
  heli-quad       copter-heli.parm + copter-heliquad.parm, model heli-quad:@ROMFS/models/heliquad.json  (FRAME_CLASS 13)
A small extra parameter file sets LOG_BITMASK 4194303. Each flight is the one of sitl-heli-logged-flight.py: the motor-interlock switch (channel 8) by RC override (low to arm, high to run
the rotor), an AUTO mission (takeoff to 20 m, a waypoint 40 m north with a 30 s loiter, return to launch), followed until the vehicle disarms or 240 s pass. The DataFlash .BIN is gzipped
and kept next to a JSON note with its size, SHA-256, the frame parameters read back, the vehicle's texts and the STAT counters before and after.
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
WORK = os.path.expanduser('~/cg-heli-variants')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter-heli')
DP = os.path.join(TREE, 'Tools/autotest/default_params')
BASE = os.path.join(DP, 'copter-heli.parm')
VARIANTS = {
    'heli-gas': ('heli-gas', [BASE, os.path.join(DP, 'copter-heli-gas.parm')]),
    'heli-ddvptail': ('heli-ddvptail', [BASE, os.path.join(DP, 'copter-heli-ddvptail.parm')]),
    'heli-ddfptail': ('heli-ddfptail', [BASE, os.path.join(DP, 'copter-heli-ddfptail.parm')]),
    'heli-dual': ('heli-dual', [BASE, os.path.join(DP, 'copter-heli-dual.parm')]),
    'heli-blade360': ('heli-blade360', [BASE]),
    'heli-quad': ('heli-quad:@ROMFS/models/heliquad.json', [BASE, os.path.join(DP, 'copter-heliquad.parm')]),
}
WANT = sys.argv[4:] or list(VARIANTS)
KEEP_PARAMS = ('FRAME_CLASS', 'FRAME_TYPE', 'H_TAIL_TYPE', 'H_RSC_MODE', 'H_RSC_RUNUP_TIME', 'RC8_OPTION', 'LOG_BITMASK', 'H_COL_MIN', 'H_COL_MAX', 'H_COL2_MIN', 'H_COL2_MAX')


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
    return {k: p[k] for k in sorted(p) if k.startswith('STAT_')}, p


def fly(name, model, defaults):
    subprocess.call(['pkill', '-x', 'arducopter-heli'])
    time.sleep(1)
    work = os.path.join(WORK, name)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    extra = os.path.join(work, 'logall.parm')
    open(extra, 'w').write('LOG_BITMASK 4194303\n')
    proc = subprocess.Popen([BIN, '-w', '--model', model, '--defaults', ','.join(defaults + [extra]), '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    notes, result, sticks = [], {'variant': name, 'model': model, 'defaults': [os.path.relpath(d, TREE) for d in defaults]}, None
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(50)
        result['stat_before'], p = stats(conn)
        result['params'] = {k: p.get(k) for k in KEEP_PARAMS}
        sticks = Sticks(conn)
        sticks.start()
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 20.0),
                 mission.Item(2, 3, 19, 0, 1, 30.0, 0, 0, 0, HOME[0] + 40 / M_LAT, HOME[1], 20.0), mission.Item(3, 3, 20, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        notes.append('STABILIZE: %s' % flight.set_mode(conn, 'STABILIZE').detail)
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            sticks.interlock = 2000
            time.sleep(25)
            sticks.collective = 1500
            notes.append('AUTO: %s' % flight.set_mode(conn, 'AUTO').detail)
            notes.append('start: %s' % flight.start_mission(conn).detail)
            begin, was = time.time(), False
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
        else:
            notes.extend('vehicle: ' + t for t in armed.texts)
        time.sleep(5)
        result['stat_after'], _ = stats(conn)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        subprocess.call(['pkill', '-x', 'arducopter-heli'])
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
    print('[%s] logs %s; %s' % (name, [k['file'] for k in kept], [n for n in notes if 'arm' in n or 'disarmed' in n or 'EXCEPTION' in n][:3]), flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in WANT:
        model, defaults = VARIANTS[name]
        fly(name, model, defaults)
    return 0


if __name__ == '__main__':
    sys.exit(main())
