"""Mode-switch sweep against disposable, disarmed SITL binaries (run in WSL with pymavlink, e.g. ~/venv-ap).

For each vehicle: start the binary with a wiped EEPROM, ask for every custom mode number 0..MAXMODE with
MAV_CMD_DO_SET_MODE, record the COMMAND_ACK result, the mode the next heartbeats report, and any STATUSTEXT.
Vehicles are never armed and nothing is flown. Writes <outdir>/mode-sweep.csv and mode-sweep.json.

    python sitl-mode-sweep.py <binary dir> <outdir>
"""
import csv
import json
import os
import subprocess
import sys
import time

from pymavlink import mavutil

VEHICLES = [  # name, binary, model, mavutil vehicle type guess
    ('ArduCopter', 'arducopter', '+'),
    ('ArduPlane', 'arduplane', 'plane'),
    ('Rover', 'ardurover', 'rover'),
    ('ArduSub', 'ardusub', 'vectored'),
    ('Blimp', 'blimp', 'blimp'),
    ('AntennaTracker', 'antennatracker', 'tracker'),
]
MAXMODE = 30


def wait_heartbeat_mode(m, want, timeout):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
        if hb is not None and hb.get_srcSystem() == m.target_system and hb.autopilot == 3:
            last = hb.custom_mode
            if last == want:
                return last
    return last


def drain(m, texts):
    while True:
        s = m.recv_match(type='STATUSTEXT', blocking=False)
        if s is None:
            return
        texts.append(s.text)


def sweep(name, binary, model, indir, outdir, instance):
    work = os.path.join(outdir, 'work-' + name)
    os.makedirs(work, exist_ok=True)
    log = open(os.path.join(work, 'sitl.log'), 'w')
    proc = subprocess.Popen([os.path.join(indir, binary), '-w', '-M', model, '-I', str(instance), '-s', '4',
                             '--home', '-35.363261,149.165230,584,0'], cwd=work, stdout=log, stderr=subprocess.STDOUT)
    port = 5760 + 10 * instance
    rows = []
    try:
        m = None
        for _ in range(40):
            try:
                m = mavutil.mavlink_connection('tcp:127.0.0.1:%d' % port, autoreconnect=False)
                break
            except Exception:
                time.sleep(0.5)
        if m is None:
            return [{'vehicle': name, 'mode': -1, 'note': 'could not connect'}]
        hb = m.wait_heartbeat(timeout=15)
        if hb is None:
            return [{'vehicle': name, 'mode': -1, 'note': 'no heartbeat'}]
        initial = hb.custom_mode
        names = mavutil.mode_mapping_bynumber(hb.type) or {}
        for mode in range(MAXMODE + 1):
            texts = []
            drain(m, texts)
            m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
                                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode, 0, 0, 0, 0, 0)
            ack = None
            end = time.time() + 3
            while time.time() < end and ack is None:
                a = m.recv_match(type='COMMAND_ACK', blocking=True, timeout=1)
                if a is not None and a.command == mavutil.mavlink.MAV_CMD_DO_SET_MODE:
                    ack = a.result
            got = wait_heartbeat_mode(m, mode, 3)
            drain(m, texts)
            rows.append({'vehicle': name, 'frame_type': hb.type, 'mode': mode, 'mode_name': names.get(mode, ''),
                         'ack_result': '' if ack is None else ack, 'heartbeat_mode_after': '' if got is None else got,
                         'switched': 'yes' if got == mode else 'no', 'initial_mode': initial,
                         'statustext': ' | '.join(texts)[:200], 'armed': 'no'})
            if got == mode and mode != initial:   # return to the initial mode before the next probe
                m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
                                        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, initial, 0, 0, 0, 0, 0)
                wait_heartbeat_mode(m, initial, 3)
        # confirm still disarmed
        hb2 = m.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
        if hb2 is not None and hb2.base_mode & 128:
            for r in rows:
                r['armed'] = 'YES'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()
    return rows


def main():
    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    allrows = []
    for i, (name, binary, model) in enumerate(VEHICLES):
        rows = sweep(name, binary, model, indir, outdir, i)
        allrows += rows
        ok = [r['mode'] for r in rows if r.get('switched') == 'yes']
        print(name, 'switched modes:', ok, flush=True)
    fields = ['vehicle', 'frame_type', 'mode', 'mode_name', 'ack_result', 'heartbeat_mode_after', 'switched', 'initial_mode',
              'statustext', 'armed', 'note']
    with open(os.path.join(outdir, 'mode-sweep.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fields, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(allrows)
    json.dump(allrows, open(os.path.join(outdir, 'mode-sweep.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
