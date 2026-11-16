"""Fault injection follow-up to ledger:lua-scripting. ArduPilot-Scripting-Trace.md already confirmed the instruction-limit removal path (lua_scripts.cpp's CPU-time hook,
"exceeded time limit") but explicitly flagged "malformed scripts" (a plain Lua runtime error, not a timeout) as never exercised. lua_scripts.cpp:347-354 shows the exact
path: lua_pcall() failing for any reason immediately calls remove_script() - the offending script is dropped from the schedule for good, not retried. This loads one
healthy, periodically-rescheduling script alongside one that throws a Lua error on its very first call, and watches whether: the error is reported once over MAVLink
("Lua: ..."), the erroring script never runs again, and the healthy script keeps going regardless - i.e. one bad script does not take anything else down with it.

    python3 sitl-lua-script-error.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import json
import os
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-lua-script-error')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')

HEALTHY_SCRIPT = """
local count = 0
function update()
  count = count + 1
  gcs:send_text(6, string.format("CODEX_LUA_HEALTHY %d", count))
  return update, 2000
end
return update, 1000
"""

ERROR_SCRIPT = """
function update()
  error("deliberate test failure from codex_error.lua")
end
return update, 1000
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    os.makedirs(os.path.join(WORK, 'scripts'))
    notes = []
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    beat = {'on': True}
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.heartbeat_send(6, 8, 0, 0, 0)

        def beats():
            while beat['on']:
                try:
                    conn.mav.heartbeat_send(6, 8, 0, 0, 0)
                except Exception:
                    return
                time.sleep(1.0)
        threading.Thread(target=beats, daemon=True).start()
        time.sleep(20)

        base = link.read_params(conn)
        bad = [r.name for r in params.write(conn, [params.Change('SCR_ENABLE', base.get('SCR_ENABLE'), 1.0)]) if not r.ok]
        notes.append('SCR_ENABLE -> 1 (rejected %s); restarting under the new setting' % bad)
        with open(os.path.join(WORK, 'scripts', 'codex_healthy.lua'), 'w') as f:
            f.write(HEALTHY_SCRIPT)
        with open(os.path.join(WORK, 'scripts', 'codex_error.lua'), 'w') as f:
            f.write(ERROR_SCRIPT)
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = subprocess.Popen([BIN, '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                                stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760, timeout=180.0)
        conn.mav.heartbeat_send(6, 8, 0, 0, 0)
        beat['on'] = True
        threading.Thread(target=beats, daemon=True).start()
        after = link.read_params(conn)
        notes.append('after restart: SCR_ENABLE=%s' % after.get('SCR_ENABLE'))

        start_t = time.time()
        while time.time() - start_t < 40.0:
            msg = conn.recv_match(type='STATUSTEXT', blocking=True, timeout=1)
            if msg is None:
                continue
            notes.append('t=%5.1f s vehicle: %s' % (time.time() - start_t, msg.text))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        beat['on'] = False
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(60)
        except Exception:
            proc.kill()
    error_hits = sum(1 for n in notes if 'codex_error.lua' in n and 'deliberate test failure' in n)
    healthy_hits = sum(1 for n in notes if 'CODEX_LUA_HEALTHY' in n)
    with open(os.path.join(OUT, 'lua-script-error-result.json'), 'w') as f:
        json.dump({'notes': notes, 'error_reported_count': error_hits, 'healthy_message_count': healthy_hits}, f, indent=1)
    print('[lua-script-error] error reported %d time(s), healthy script ran %d time(s)' % (error_hits, healthy_hits), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
