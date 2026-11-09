"""Execution evidence for ArduPilot libraries and modes that only run in flight, from disposable simulators (WSL, pymavlink, the custom-gcs library). Simulator only.

    python3 sitl-aerial-evidence.py <ardupilot tree> <out dir> <custom-gcs dir> [part ...]     parts: copter-log, plane-log, heli-acro, custom-mode

copter-log   a Copter flown through a mission with every log bit enabled (LOG_BITMASK 4194303) and LOG_REPLAY 1 set before boot; the DataFlash .BIN is kept (gzipped), and the
             STAT_* parameters are read before and after the flight (AP_Stats counts flight time and boots).
plane-log    the same for a fixed-wing Plane: takeoff, three waypoints, an automatic landing (the TECS, L1 and landing code run).
heli-acro    arducopter-heli (the only build that contains ModeAcro_Heli): ACRO requested disarmed, then armed on the ground; the mode the vehicle reports, the vehicle's text and
             the log's MODE messages are kept.
custom-mode  a Copter with SCR_ENABLE 1 and libraries/AP_Scripting/examples/Flip_Mode.lua, which registers custom mode 100 through vehicle:register_custom_mode (the only way into
             ArduCopter/mode_guided_custom.cpp): mode 100 is requested on the ground and then in flight from ALT_HOLD; the answers and the vehicle's text are kept.
"""
import gzip
import json
import math
import os
import shutil
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
PARTS = sys.argv[4:] or ['copter-log', 'plane-log', 'heli-acro', 'custom-mode']
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-aerial')
LOG_ALL = 4194303


def say(prefix, text):
    print('[%s] %s' % (prefix, text), flush=True)
    return text


def start(binary, model, wipe):
    return subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/' + binary)] + (['-w'] if wipe else []) + ['--model', model, '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def stop(proc):
    proc.terminate()
    try:
        proc.wait(10)
    except Exception:
        proc.kill()


def set_params(conn, values):
    base = link.read_params(conn)
    bad = [r for r in params.write(conn, [params.Change(n, base.get(n), float(v)) for n, v in values.items()]) if not r.ok]
    if bad:
        raise RuntimeError('could not set %s' % [b.name for b in bad])


def boot(binary, model, preset, script=None):
    """First start sets `preset` parameters (they must exist from boot), a second start without wiping keeps them. Returns (proc, conn, mav_type)."""
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(os.path.join(WORK, 'scripts'))
    if preset:
        proc = start(binary, model, True)
        try:
            conn, _ = link.connect(5760)
            time.sleep(15)
            set_params(conn, preset)
            time.sleep(2)
        finally:
            stop(proc)
        if script:
            subprocess.call(['cp', os.path.join(TREE, 'libraries/AP_Scripting/examples', script), os.path.join(WORK, 'scripts')])
    proc = start(binary, model, not preset)
    conn, mav_type = link.connect(5760)
    return proc, conn, mav_type


def keep_logs(proc, name):
    stop(proc)
    time.sleep(1)
    logs = os.path.join(WORK, 'logs')
    kept = []
    if os.path.isdir(logs):
        for f in sorted(os.listdir(logs)):
            if f.endswith('.BIN'):
                target = os.path.join(OUT, '%s-%s.gz' % (name, f))
                with open(os.path.join(logs, f), 'rb') as src, gzip.open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                kept.append(os.path.basename(target))
    return kept


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def item(seq, command, point=(0.0, 0.0), alt=0.0, p1=0.0):
    return mission.Item(seq, 3, command, 1 if seq == 1 else 0, 1, p1, 0, 0, 0, point[0], point[1], alt)


def fly(conn, table, items, limit, notes):
    """Upload, arm, AUTO (+ start for a Copter), follow until the vehicle disarms or `limit` seconds pass. Returns True if it disarmed."""
    notes.append('upload ack %s' % mission.upload(conn, items))
    flight.set_mode(conn, 'STABILIZE' if table == 'copter' else 'MANUAL', table=table)
    armed = flight.arm(conn, timeout=150.0)
    notes.append('arm: %s' % armed.detail)
    if not armed.ok:
        return False
    auto = flight.set_mode(conn, 'AUTO', table=table)
    give_up = time.time() + 90.0
    while not auto.ok and time.time() < give_up:
        time.sleep(3)
        auto = flight.set_mode(conn, 'AUTO', table=table)
    notes.append('AUTO: %s' % auto.detail)
    if not auto.ok:
        return False
    if table == 'copter':
        notes.append('start: %s' % flight.start_mission(conn).detail)
    start_time, last_hb = time.time(), None
    while time.time() - start_time < limit:
        msg = conn.recv_match(type=['HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
        if msg is None:
            continue
        if msg.get_type() == 'STATUSTEXT':
            notes.append('t=%5.1f vehicle: %s' % (time.time() - start_time, msg.text))
        elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
            if last_hb is not None and flight.is_armed(last_hb) != flight.is_armed(msg) and not flight.is_armed(msg):
                notes.append('t=%5.1f disarmed' % (time.time() - start_time))
                return True
            last_hb = msg
    return False


def stat_params(conn):
    p = link.read_params(conn)
    return {k: p[k] for k in sorted(p) if k.startswith('STAT_')}


def logged_flight(name, binary, table, items, limit):
    notes, result = [], {}
    proc = None
    try:
        proc, conn, _ = boot(binary, 'plane' if table == 'plane' else '+', {'LOG_BITMASK': LOG_ALL, 'LOG_REPLAY': 1})
        time.sleep(45)
        result['stat_before'] = stat_params(conn)
        result['disarmed_by_itself'] = fly(conn, table, items, limit, notes)
        time.sleep(5)
        result['stat_after'] = stat_params(conn)
        base = link.read_params(conn)
        result['log_bitmask'] = base.get('LOG_BITMASK')
        result['log_replay'] = base.get('LOG_REPLAY')
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        result['logs'] = keep_logs(proc, name) if proc else []
    result['notes'] = notes
    with open(os.path.join(OUT, name + '.json'), 'w') as f:
        json.dump(result, f, indent=1)
    say(name, 'logs %s, disarmed by itself %s' % (result['logs'], result.get('disarmed_by_itself')))


def copter_log():
    items = [item(0, 16, at(0, 0), HOME[2]), item(1, 22, alt=15.0), item(2, 16, at(78, 0), 15.0), item(3, 16, at(78, 82), 15.0), item(4, 20)]
    items[0] = mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2])
    logged_flight('copter-logged-flight', 'arducopter', 'copter', items, 240.0)


def plane_log():
    a, b, c = at(300, 0), at(300, 300), at(0, 300)
    items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), item(1, 22, alt=60.0, p1=15.0), item(2, 16, a, 60.0), item(3, 16, b, 60.0), item(4, 16, c, 40.0),
             item(5, 21, (HOME[0], HOME[1]), 0.0)]
    logged_flight('plane-logged-flight', 'arduplane', 'plane', items, 240.0)


def heli_acro():
    notes, proc = [], None
    try:
        proc, conn, _ = boot('arducopter-heli', 'heli', {'LOG_BITMASK': LOG_ALL})
        time.sleep(45)
        notes.append('mode before: %s' % flight.current_mode(conn))
        r = flight.set_mode(conn, 'ACRO')
        notes.append('ACRO disarmed: %s | %s' % (r.detail, '; '.join(r.texts[-3:])))
        time.sleep(3)
        notes.append('mode after: %s' % flight.current_mode(conn))
        armed = flight.arm(conn, timeout=60.0)
        notes.append('arm: %s | %s' % (armed.detail, '; '.join(armed.texts[-3:])))
        r = flight.set_mode(conn, 'ACRO')
        notes.append('ACRO armed: %s | %s' % (r.detail, '; '.join(r.texts[-3:])))
        time.sleep(5)
        notes.append('mode after: %s' % flight.current_mode(conn))
        notes.append('disarm: %s' % flight.disarm(conn).detail)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        logs = keep_logs(proc, 'heli-acro') if proc else []
    with open(os.path.join(OUT, 'heli-acro.json'), 'w') as f:
        json.dump({'notes': notes, 'logs': logs}, f, indent=1)
    say('heli-acro', '; '.join(notes))


def custom_mode():
    notes, proc = [], None
    try:
        proc, conn, _ = boot('arducopter', '+', {'SCR_ENABLE': 1, 'LOG_BITMASK': LOG_ALL}, script='Flip_Mode.lua')
        time.sleep(45)
        notes.append('mode before: %s' % flight.current_mode(conn))
        # the custom number is not in the generated table; send DO_SET_MODE directly
        def request(number):
            conn.mav.command_long_send(conn.target_system, conn.target_component, 176, 0, 1, number, 0, 0, 0, 0, 0)
            texts, acks, end, hb = [], [], time.time() + 5, None
            while time.time() < end:
                msg = conn.recv_match(type=['HEARTBEAT', 'COMMAND_ACK', 'STATUSTEXT'], blocking=True, timeout=0.5)
                if msg is None:
                    continue
                if msg.get_type() == 'STATUSTEXT':
                    texts.append(msg.text)
                elif msg.get_type() == 'COMMAND_ACK':
                    acks.append(msg.result)
                elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    hb = msg
            return 'ack %s, mode number %s, texts %s' % (acks[-1] if acks else None, hb.custom_mode if hb else None, texts[-3:])
        notes.append('custom mode 100 on the ground, disarmed: ' + request(100))
        flight.set_mode(conn, 'STABILIZE')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        notes.append('custom mode 100 on the ground, armed: ' + request(100))
        # take off with a one-item mission, then ALT_HOLD, then mode 100
        mission.upload(conn, [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), item(1, 22, alt=20.0), item(2, 16, at(60, 0), 20.0)])
        flight.set_mode(conn, 'AUTO')
        notes.append('start: %s' % flight.start_mission(conn).detail)
        time.sleep(14)
        notes.append('height check: mode %s' % flight.current_mode(conn))
        notes.append('ALT_HOLD in flight: %s' % flight.set_mode(conn, 'ALT_HOLD').detail)
        time.sleep(2)
        notes.append('custom mode 100 in flight from ALT_HOLD: ' + request(100))
        time.sleep(3)
        notes.append('mode after: %s' % flight.current_mode(conn))
        flight.set_mode(conn, 'LAND')
        time.sleep(30)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        logs = keep_logs(proc, 'custom-mode') if proc else []
    with open(os.path.join(OUT, 'custom-mode.json'), 'w') as f:
        json.dump({'notes': notes, 'logs': logs}, f, indent=1)
    say('custom-mode', ' | '.join(notes))


def main():
    os.makedirs(OUT, exist_ok=True)
    for part in PARTS:
        {'copter-log': copter_log, 'plane-log': plane_log, 'heli-acro': heli_acro, 'custom-mode': custom_mode}[part]()
    return 0


if __name__ == '__main__':
    sys.exit(main())
