"""Confirms the source-level explanation of the MAV_CMD_DO_CHANGE_ALTITUDE hang: ArduPlane/GCS_MAVLink_Plane.cpp:handle_command_int_DO_CHANGE_ALTITUDE always builds
Location{lat=0, lng=0, alt_cm, frame} (the command is altitude-only, no horizontal position), then calls Location::get_alt_cm() on it; the SITL-only check in that function panics if the
location is the literal triple (0, 0, 0). With all parameters zero (as sitl-mavlink-command-sweep.py sends by design) the altitude is 0 too, matching the panic exactly. A genuinely non-zero
altitude should build Location{0, 0, nonzero_cm, frame}, not match (0,0,0), and so should not panic. Tests DO_CHANGE_ALTITUDE with altitude=50 m, both COMMAND_LONG and COMMAND_INT, against
a fresh ArduPlane. Simulator only (WSL, pymavlink).

    python3 sitl-confirm-change-altitude-nonzero.py <ardupilot tree> <out dir>
"""
import json
import os
import subprocess
import sys
import time

TREE, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.expanduser('~/custom-gcs'))
from customgcs import link  # noqa: E402

HOME = '-35.363261,149.165230,584,0'
WORK = os.path.expanduser('~/cg-confirm-alt')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
DEFAULTS = os.path.join(TREE, 'Tools/autotest/models/plane.parm')
NUMBER = 186  # MAV_CMD_DO_CHANGE_ALTITUDE


def one(kind, altitude_m):
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    work = os.path.join(WORK, '%s-%s' % (kind, str(altitude_m).replace('.', '_')))
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([BIN, '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', HOME, '--defaults', DEFAULTS], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    result = {'kind': kind, 'altitude_m': altitude_m}
    try:
        conn, _ = link.connect(5760, timeout=60.0)
        time.sleep(45)
        result['alive_before_send'] = proc.poll() is None
        if kind == 'LONG':
            conn.mav.command_long_send(conn.target_system, conn.target_component, NUMBER, 0, float(altitude_m), 0, 0, 0, 0, 0, 0)  # param1=altitude(m), param2=frame(0=GLOBAL)
        else:
            conn.mav.command_int_send(conn.target_system, conn.target_component, 0, NUMBER, 0, 0, float(altitude_m), 0, 0, 0, 0, 0, 0)  # param1=altitude(m) per the handler, x/y/z unused
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        result['ack'] = None if ack is None else ack.result
        time.sleep(5)
        result['alive_after_send'] = proc.poll() is None
        # a follow-up command on the same link, to show it was not left hung
        conn.mav.command_long_send(conn.target_system, conn.target_component, 400, 0, 0, 0, 0, 0, 0, 0, 0)  # MAV_CMD_COMPONENT_ARM_DISARM, disarm (harmless, already disarmed)
        ack2 = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        result['followup_ack'] = None if ack2 is None else ack2.result
    except Exception as e:
        result['exception'] = repr(e)
    finally:
        subprocess.call(['pkill', '-x', 'arduplane'])
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    log_tail = open(os.path.join(work, 'sitl.log'), errors='replace').read().splitlines()[-4:]
    result['log_tail'] = log_tail
    print('[%s alt=%s] ack=%s followup_ack=%s alive_after=%s tail=%s' % (kind, altitude_m, result.get('ack'), result.get('followup_ack'), result.get('alive_after_send'), log_tail[-1:]), flush=True)
    return result


def main():
    os.makedirs(OUT, exist_ok=True)
    results = [one('LONG', 50.0), one('INT', 50.0), one('LONG', 0.0)]  # the last repeats the zero case for a direct side-by-side
    json.dump(results, open(os.path.join(OUT, 'confirm-results.json'), 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
