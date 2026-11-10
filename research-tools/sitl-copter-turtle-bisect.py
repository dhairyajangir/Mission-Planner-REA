"""Why does the earlier turtle-entry test get TURTLE (mode 28) accepted while the harness of sitl-copter-untested-modes.py is refused? One difference at a time, each on a fresh simulator boot
(arducopter -w --model +, speedup 1, no debugger). Simulator only (WSL, pymavlink).

    python3 sitl-copter-turtle-bisect.py <arducopter binary> <outdir>

Every case sets SERVO_DSHOT_ESC to 1, keeps the RC override on channels 1 to 4 at 1500 and then asks for TURTLE once. The control copies the earlier test (param_set as INT8, RC override pumped
inline, data stream requested, three failed TURTLE requests first). The other cases change exactly one thing from the control:
  control        as the earlier test
  real32         parameter written as MAV_PARAM_TYPE_REAL32 (what the prototype's params.write does)
  thread         RC override sent from a thread at 10 Hz instead of inline in the receive loop
  no-stream      no REQUEST_DATA_STREAM
  no-prior       no failed TURTLE requests before the one that counts
  sid-axis       SID_AXIS set to 1 as well
  late           the request is made 60 s after the parameter instead of 6 s
  instance0      simulator instance 0 (-I 0, TCP 5760) instead of -I 7 (TCP 5830), which is what sitl-copter-untested-modes.py uses
  read-params    the whole parameter list is downloaded (PARAM_REQUEST_LIST) before the first request
  all-harness    every difference from the control that sitl-copter-untested-modes.py has, together (instance 0, parameter download, REAL32 writes, RC thread, SID_AXIS, no stream, no prior attempts, late request)
  BISECT_ONLY=a,b   run only the named cases (results go to turtle-bisect-<names>.json/csv)
"""
import csv
import json
import os
import subprocess
import sys
import threading
import time

from pymavlink import mavutil

TURTLE = 28
CASES = [('control', {}), ('real32', {'real32': True}), ('thread', {'thread': True}), ('no-stream', {'stream': False}), ('no-prior', {'prior': False}), ('sid-axis', {'sid': True}),
         ('late', {'late': True}), ('instance0', {'instance': 0}), ('read-params', {'read_params': True}), ('instance0-read-params', {'instance': 0, 'read_params': True}),
         ('all-harness', {'instance': 0, 'read_params': True, 'real32': True, 'thread': True, 'sid': True, 'stream': False, 'prior': False, 'late': True})]


class Link:
    def __init__(self, m, thread):
        self.m, self.hb, self.texts, self.rc, self.thread = m, None, [], False, thread
        if thread:
            threading.Thread(target=self._sender, daemon=True).start()

    def _send(self):
        self.m.mav.rc_channels_override_send(self.m.target_system, self.m.target_component, 1500, 1500, 1500, 1500, 0, 0, 0, 0)

    def _sender(self):
        while True:
            if self.rc:
                try:
                    self._send()
                except Exception:
                    pass
            time.sleep(0.1)

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if self.rc and not self.thread:
                self._send()
            msg = self.m.recv_match(blocking=True, timeout=0.1)
            if msg is None:
                continue
            t = msg.get_type()
            if t == 'HEARTBEAT' and msg.autopilot == 3:
                self.hb = msg
            elif t == 'STATUSTEXT':
                self.texts.append(msg.text)

    def set_param(self, name, value, real32):
        ptype = mavutil.mavlink.MAV_PARAM_TYPE_REAL32 if real32 else mavutil.mavlink.MAV_PARAM_TYPE_INT8
        self.m.mav.param_set_send(self.m.target_system, self.m.target_component, name.encode(), float(value), ptype)
        self.pump(1.0)

    def try_turtle(self):
        self.texts.clear()
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, TURTLE, 0, 0, 0, 0, 0)
        ack = self.m.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        self.pump(2.0)
        return {'ack_result': None if ack is None else ack.result, 'custom_mode': None if self.hb is None else self.hb.custom_mode, 'statustext': ' | '.join(self.texts)[:200]}


def run_case(binary, outdir, name, opt, port):
    work = os.path.join(outdir, name)
    os.makedirs(work, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])        # exact name: -f would match this script's own command line
    time.sleep(1)
    log = open(os.path.join(work, 'sitl.log'), 'w')
    instance = opt.get('instance', 7)
    port = 5760 + 10 * instance
    proc = subprocess.Popen([binary, '-w', '-M', '+', '-I', str(instance), '-s', '1', '--home', '-35.363261,149.165230,584,0'], cwd=work, stdout=log, stderr=subprocess.STDOUT)
    result = {'case': name, 'options': opt}
    try:
        m = None
        for _ in range(120):
            try:
                m = mavutil.mavlink_connection('tcp:127.0.0.1:%d' % (5760 + 10 * opt.get('instance', 7)), autoreconnect=False)
                break
            except Exception:
                time.sleep(0.5)
        m.wait_heartbeat(timeout=60)
        L = Link(m, opt.get('thread', False))
        if opt.get('stream', True):
            m.mav.request_data_stream_send(m.target_system, m.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
        t0 = time.time()
        while time.time() - t0 < 180:
            L.pump(0.5)
            if any('using GPS' in t for t in L.texts):
                break
        L.pump(3)
        if opt.get('read_params'):
            m.mav.param_request_list_send(m.target_system, m.target_component)
            L.pump(25.0)
        if opt.get('prior', True):
            result['prior_attempts'] = [L.try_turtle()['ack_result'] for _ in range(1)]
            L.rc = True
            L.pump(1.0)
            result['prior_attempts'].append(L.try_turtle()['ack_result'])
            L.rc = False
            L.set_param('SERVO_DSHOT_ESC', 1, opt.get('real32', False))
            if opt.get('sid'):
                L.set_param('SID_AXIS', 1, opt.get('real32', False))
            L.pump(5.0)
            result['prior_attempts'].append(L.try_turtle()['ack_result'])
        else:
            L.set_param('SERVO_DSHOT_ESC', 1, opt.get('real32', False))
            if opt.get('sid'):
                L.set_param('SID_AXIS', 1, opt.get('real32', False))
        L.rc = True
        L.pump(60.0 if opt.get('late') else 1.0)
        result['final'] = L.try_turtle()
    except Exception as e:
        result['error'] = repr(e)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        log.close()
    print(json.dumps(result), flush=True)
    return result


def main():
    binary, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    only = [n for n in os.environ.get('BISECT_ONLY', '').split(',') if n]
    suffix = '-' + '+'.join(only) if only else ''
    results = [run_case(binary, outdir, name, opt, 5830) for name, opt in CASES if not only or name in only]
    json.dump(results, open(os.path.join(outdir, 'turtle-bisect%s.json' % suffix), 'w'), indent=1)
    with open(os.path.join(outdir, 'turtle-bisect%s.csv' % suffix), 'w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['case', 'options', 'prior_acks', 'final_ack', 'final_mode', 'final_text', 'error'])
        for r in results:
            fin = r.get('final', {})
            w.writerow([r['case'], json.dumps(r['options']), r.get('prior_attempts'), fin.get('ack_result'), fin.get('custom_mode'), fin.get('statustext'), r.get('error', '')])


if __name__ == '__main__':
    main()
