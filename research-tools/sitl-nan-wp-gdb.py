"""Reproduce the NaN-latitude MISSION_ITEM (float) simulator abort under gdb. WSL, disposable SITL only.

Starts the Copter SITL binary under gdb (SIGFPE stops and is printed with a backtrace), connects with pymavlink,
sends MISSION_COUNT 1 then one float MISSION_ITEM whose x (latitude) is NaN, and waits for gdb to report.

    python sitl-nan-wp-gdb.py <arducopter binary> <outdir> [nan|inf|valid]
"""
import os
import subprocess
import sys
import time

from pymavlink import mavutil

binary, outdir = sys.argv[1], sys.argv[2]
variant = sys.argv[3] if len(sys.argv) > 3 else 'nan'
os.makedirs(outdir, exist_ok=True)
gdbcmds = os.path.join(outdir, 'cmds.gdb')
open(gdbcmds, 'w').write('handle SIGFPE stop nopass print\nhandle SIGPIPE nostop noprint pass\nrun\nbt 25\ninfo registers rip\nx/6i $rip-12\ninfo signal SIGFPE\nquit\n')
out = open(os.path.join(outdir, 'gdb-%s.log' % variant), 'w')
proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdbcmds, '--args', binary, '-w', '-M', '+', '-I', '5', '-s', '1',
                         '--home', '-35.363261,149.165230,584,0'], cwd=outdir, stdout=out, stderr=subprocess.STDOUT)
try:
    m = None
    for _ in range(60):
        try:
            m = mavutil.mavlink_connection('tcp:127.0.0.1:5810', autoreconnect=False)
            break
        except Exception:
            time.sleep(0.5)
    m.wait_heartbeat(timeout=30)
    value = {'nan': float('nan'), 'inf': float('inf'), 'valid': -35.36}[variant]
    m.mav.mission_count_send(m.target_system, m.target_component, 2, 0)
    req = m.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=5)
    print('request after count:', None if req is None else req.get_type(), None if req is None else req.seq, flush=True)
    # item 0: home (valid), item 1: the item under test, floating-point message
    m.mav.mission_item_send(m.target_system, m.target_component, 0, mavutil.mavlink.MAV_FRAME_GLOBAL, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                            0, 1, 0, 0, 0, 0, -35.363261, 149.16523, 584, 0)
    req = m.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=5)
    print('request after item 0:', None if req is None else req.get_type(), None if req is None else req.seq, flush=True)
    m.mav.mission_item_send(m.target_system, m.target_component, 1, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                            0, 1, 0, 0, 0, 0, value, 149.16523, 20, 0)
    ack = m.recv_match(type='MISSION_ACK', blocking=True, timeout=8)
    print('ack:', None if ack is None else ack.type, flush=True)
except Exception as e:
    print('client error:', e, flush=True)
try:
    proc.wait(timeout=20)
except subprocess.TimeoutExpired:
    proc.terminate()
    proc.wait(timeout=10)
out.close()
print('gdb exit', proc.returncode)
