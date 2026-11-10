"""The multicopter frames of the simulator, each flown once with full DataFlash logging. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-copter-variants.py <ardupilot tree> <out dir> <custom-gcs dir> [frame ...]

Every internal frame of `Tools/autotest/pysim/vehicleinfo.json` for ArduCopter that does not need an external simulator or a CAN peripheral is started as `arducopter -w --model <model>
--defaults <files>` with the frame's own default-parameter files plus a one-line file setting LOG_BITMASK 4194303. One mission as in sitl-heli-variants.py: armed in STABILIZE, an AUTO mission
(takeoff to 20 m, a waypoint 40 m north with a 30 s loiter, return to launch), started with MAV_CMD_MISSION_START, followed to disarm or 240 s. The DataFlash .BIN is gzipped next to a JSON
note with its size, SHA-256, the frame parameters read back, the vehicle's texts with times and the STAT counters before and after.
The three FRAME_CLASS 15 (dynamic matrix) frames need their Lua motor-matrix example script: ArduPilot's FlyEachFrame copies it (`frame_example_script` in vehicleinfo.json), sets SCR_ENABLE 1 and
restarts the simulator. SCRIPTED_FRAMES=1 does the same here (script copied to ./scripts, SCR_ENABLE 1 in the extra parameter file, one restart without wiping before arming); without it those
frames cannot be armed ("Motors: Check frame class and type").
"""
import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
WORK = os.path.expanduser('~/cg-copter-variants')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
T = os.path.join(TREE, 'Tools/autotest')


def dp(*names):
    return [os.path.join(T, 'default_params', n + '.parm') if not n.startswith('models/') else os.path.join(T, n + '.parm') for n in names]


# frame: (model, [default files without .parm])
FRAMES = {
    '+': ('+', ['copter']), 'X': ('X', ['copter', 'copter-X']), 'bfx': ('bfx', ['copter', 'copter-bfx']), 'djix': ('djix', ['copter', 'copter-djix']), 'cwx': ('cwx', ['copter', 'copter-cwx']),
    'hexa': ('hexa', ['copter', 'copter-hexa']), 'hexax': ('hexax', ['copter', 'copter-hexa', 'copter-X']), 'hexa-cwx': ('hexa-cwx', ['copter', 'copter-hexa', 'copter-hexa-cwx']),
    'hexa-dji': ('hexa-dji', ['copter', 'copter-hexa', 'copter-hexa-dji']), 'octa': ('octa', ['copter', 'copter-octa']), 'octa-dji': ('octa-dji', ['copter', 'copter-octa', 'copter-octa-dji']),
    'octa-cwx': ('octa-cwx', ['copter', 'copter-octa', 'copter-octa-cwx']), 'octa-quad': ('octa-quad', ['copter', 'copter-octaquad']),
    'octa-quad-cwx': ('octa-quad-cwx', ['copter', 'copter-octaquad', 'copter-octaquad-cwx']), 'octa-quad-cor': ('octa-quad-cor', ['copter', 'copter-octaquad-cor']),
    'octa-quad-cw-cor': ('octa-quad-cw-cor', ['copter', 'copter-octaquad-cw-cor']), 'deca': ('deca', ['copter', 'copter-deca']), 'deca-cwx': ('deca-cwx', ['copter', 'copter-deca', 'copter-deca-cwx']),
    'tri': ('tri', ['copter', 'copter-tri']), 'y6': ('y6', ['copter', 'copter-y6']), 'dodeca-hexa': ('dodeca-hexa', ['copter', 'copter-dodecahexa']),
    'dotriaconta_octaquad_x': ('dotriaconta_octaquad_x', ['copter', 'copter-dotriaconta_octaquad_x']), 'hexadeca-octa': ('hexadeca-octa', ['copter', 'copter-hexadeca_octa']),
    'hexadeca-octa-cwx': ('hexadeca-octa-cwx', ['copter', 'copter-hexadeca_octa', 'copter-hexadeca_octa_cwx']), 'singlecopter': ('singlecopter', ['copter-single']),
    'coaxcopter': ('coaxcopter', ['copter-single', 'copter-coax']), 'Callisto': ('octa-quad-cwx:@ROMFS/models/Callisto.json', ['copter', 'copter-octaquad', 'models/Callisto']),
    'freestyle': ('X:@ROMFS/models/freestyle.json', ['copter', 'copter-X', 'models/freestyle']),
}
WANT = sys.argv[4:] or list(FRAMES)
SCRIPTED = bool(os.environ.get('SCRIPTED_FRAMES'))
FRAME_SCRIPTS = {'dotriaconta_octaquad_x': 'MotorMatrix_dotriaconta_octaquad_x.lua', 'hexadeca-octa': 'MotorMatrix_hexadeca_octa.lua', 'hexadeca-octa-cwx': 'MotorMatrix_hexadeca_octa_cw_x.lua'}
KEEP = ('FRAME_CLASS', 'FRAME_TYPE', 'LOG_BITMASK', 'MOT_THST_HOVER', 'MOT_PWM_TYPE', 'ATC_RAT_RLL_P', 'ATC_RAT_PIT_P', 'ATC_RAT_YAW_P')


def safe(name):
    return name.replace('+', 'plus')


def stats(conn):
    p = link.read_params(conn)
    return {k: p[k] for k in sorted(p) if k.startswith('STAT_')}, p


def fly(name, model, files):
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    work = os.path.join(WORK, safe(name))
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    extra = os.path.join(work, 'logall.parm')
    open(extra, 'w').write('LOG_BITMASK 4194303\n' + ('SCR_ENABLE 1\n' if SCRIPTED and name in FRAME_SCRIPTS else ''))
    if SCRIPTED and name in FRAME_SCRIPTS:
        os.makedirs(os.path.join(work, 'scripts'))
        subprocess.call(['cp', os.path.join(TREE, 'libraries/AP_Scripting/examples', FRAME_SCRIPTS[name]), os.path.join(work, 'scripts')])
    defaults = dp(*files)
    missing = [d for d in defaults if not os.path.isfile(d)]
    result = {'frame': name, 'model': model, 'defaults': [os.path.relpath(d, TREE) for d in defaults], 'missing_default_files': missing}
    notes, proc = [], None
    if missing:
        notes.append('default files missing: %s' % missing)
    else:
        proc = subprocess.Popen([BIN, '-w', '--model', model, '--defaults', ','.join(defaults + [extra]), '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                                stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
        try:
            conn, mav_type = link.connect(5760, timeout=120.0)
            result['mav_type'] = mav_type
            time.sleep(45)
            result['stat_before'], p = stats(conn)
            result['params'] = {k: p.get(k) for k in KEEP}
            if SCRIPTED and name in FRAME_SCRIPTS:
                notes.append('script %s installed, SCR_ENABLE 1: restarting the simulator once, without wiping' % FRAME_SCRIPTS[name])
                subprocess.call(['pkill', '-x', 'arducopter'])
                try:
                    proc.wait(15)
                except Exception:
                    proc.kill()
                time.sleep(2)
                proc = subprocess.Popen([BIN, '--model', model, '--defaults', ','.join(defaults + [extra]), '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                                        stdout=open(os.path.join(work, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
                conn, _ = link.connect(5760, timeout=120.0)
                time.sleep(60)
                result['stat_before'], p = stats(conn)
                result['params_after_restart'] = {k: p.get(k) for k in KEEP + ('SCR_ENABLE',)}
            items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 20.0),
                     mission.Item(2, 3, 19, 0, 1, 30.0, 0, 0, 0, HOME[0] + 40 / M_LAT, HOME[1], 20.0), mission.Item(3, 3, 20, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0)]
            notes.append('upload ack %s' % mission.upload(conn, items))
            flight.set_mode(conn, 'STABILIZE')
            armed = flight.arm(conn, timeout=120.0)
            notes.append('arm: %s' % armed.detail)
            if armed.ok:
                auto = flight.set_mode(conn, 'AUTO')
                notes.append('AUTO: %s' % auto.detail)
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
            subprocess.call(['pkill', '-x', 'arducopter'])
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
                target = os.path.join(OUT, '%s-logged-flight-%s.gz' % (safe(name), f))
                with gzip.open(target, 'wb') as dst:
                    dst.write(raw)
                kept.append({'file': os.path.basename(target), 'raw_bytes': len(raw), 'gz_bytes': os.path.getsize(target), 'gz_sha256': hashlib.sha256(open(target, 'rb').read()).hexdigest()})
    result.update({'notes': notes, 'logs': kept})
    with open(os.path.join(OUT, '%s-logged-flight.json' % safe(name)), 'w') as f:
        json.dump(result, f, indent=1)
    print('[%s] logs %d; %s' % (name, len(kept), [n for n in notes if 'arm:' in n or 'disarmed' in n or 'EXCEPTION' in n or 'missing' in n][:3]), flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in WANT:
        model, files = FRAMES[name]
        fly(name, model, files)
    return 0


if __name__ == '__main__':
    sys.exit(main())
