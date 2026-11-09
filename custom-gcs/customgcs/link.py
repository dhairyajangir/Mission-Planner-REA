"""Talk to a vehicle with pymavlink: read its parameters, run a motor test plan, and report which servo outputs actually moved.

Simulator use only so far. The motor test sends commands that spin motors: never run it with propellers on or against a real aircraft.
"""
import time
from dataclasses import dataclass
from typing import Dict, List, Mapping, Tuple

from .motors import Step, plan, motor_number, servo_functions, servo_of_motor
from .vehicle import VehicleInfo, detect

_STATE = [0] * 32       # latest value of outputs 1..32, shared between reads so a port 0 message does not erase port 1 values
MOVED_US = 20            # an output counts as moved when it leaves its value at the start of the step by this much or more


@dataclass(frozen=True)
class StepResult:
    label: str
    expected: Tuple[int, ...]
    moved: Tuple[int, ...]
    ok: bool
    note: str = ''


def connect(port: int, host: str = '127.0.0.1', timeout: float = 60.0):
    from pymavlink import mavutil
    end = time.time() + timeout
    while time.time() < end:
        try:
            link = mavutil.mavlink_connection('tcp:%s:%d' % (host, port), autoreconnect=False)
            hb = link.wait_heartbeat(timeout=30)
            return link, hb.type
        except Exception:
            time.sleep(1)
    raise TimeoutError('no heartbeat on %s:%d' % (host, port))


def read_params(link, quiet_seconds: float = 8.0) -> Dict[str, float]:
    """Download the whole parameter list once (single-name requests proved unreliable; see Setup-Page-Disabled-Reasons-Trace.md)."""
    link.mav.param_request_list_send(link.target_system, link.target_component)
    params: Dict[str, float] = {}
    count = None
    last = time.time()
    while time.time() - last < quiet_seconds and (count is None or len(params) < count):
        msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg is None:
            continue
        last = time.time()
        count = msg.param_count
        params[msg.param_id.rstrip('\x00')] = msg.param_value
    return params


OUTPUT_COUNT = 32


def _outputs(msg, state: List[int]) -> List[int]:
    """SERVO_OUTPUT_RAW carries 16 outputs per message; `port` 0 is outputs 1..16 and port 1 is 17..32. Keep the latest value of all 32 and return a copy."""
    base = 16 * getattr(msg, 'port', 0)
    for i in range(16):
        if base + i < OUTPUT_COUNT:
            state[base + i] = getattr(msg, 'servo%d_raw' % (i + 1), 0)
    return list(state)


def _drain(link, seconds: float, send=None, every: float = 0.25, events=None) -> List[List[int]]:
    """Collect SERVO_OUTPUT_RAW rows for `seconds`, sending `send()` every `every` seconds. With `events` (a list), also record ('ack', result) for motor-test
    command acknowledgements and ('text', message) for STATUSTEXT."""
    from pymavlink import mavutil
    rows, end, last = [], time.time() + seconds, 0.0
    state = _STATE
    while time.time() < end:
        if send and time.time() - last >= every:
            send()
            last = time.time()
        msg = link.recv_match(type=['SERVO_OUTPUT_RAW', 'COMMAND_ACK', 'STATUSTEXT'], blocking=True, timeout=0.1)
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == 'SERVO_OUTPUT_RAW':
            rows.append(_outputs(msg, state))
        elif events is not None and kind == 'COMMAND_ACK' and msg.command == mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST:
            events.append(('ack', msg.result))
        elif events is not None and kind == 'STATUSTEXT':
            events.append(('text', msg.text))
    return rows


def monitored_outputs(params: Mapping[str, float]) -> Tuple[int, ...]:
    """Outputs worth watching: motors, throttles (70, 73, 74), tilt servos (75, 76) and steering (26). Control surfaces move by themselves on a QuadPlane and are left out."""
    return tuple(sorted(n for n, f in servo_functions(params).items() if motor_number(f) is not None or f in (26, 70, 73, 74, 75, 76)))


READY_TIMEOUT_S = 60.0   # a Rover rejects motor tests (COMMAND_ACK result 4, "Arm: Accels inconsistent") for about 12 s after start although its heartbeat already says ACTIVE


def run_step(link, step: Step, baseline: List[int], watch: Tuple[int, ...] = (), ready_timeout: float = READY_TIMEOUT_S) -> Tuple[StepResult, List[int]]:
    """Send the step and watch the outputs. If the vehicle rejects the command (COMMAND_ACK other than ACCEPTED, none accepted), try again until `ready_timeout`."""
    from pymavlink import mavutil
    p = step.params
    send = lambda: link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0, *p)
    seconds = max(p[3] + 0.8, 1.4) if step.repeat_every_s is None else p[3] + 0.4
    deadline, tries = time.time() + ready_timeout, 0
    while True:
        events: list = []
        rows = _drain(link, seconds, send, step.repeat_every_s or max(seconds, 10.0), events)
        tries += 1
        acks = [r for kind, r in events if kind == 'ack']
        if not acks or 0 in acks or time.time() >= deadline:
            break
        time.sleep(1)
    rejection = ''
    if acks and 0 not in acks:
        texts = [t for kind, t in events if kind == 'text']
        rejection = 'rejected (ack result %d%s) after %d tries' % (acks[-1], ', ' + texts[-1] if texts else '', tries)
    note = rejection or ('accepted after %d tries' % tries if tries > 1 else '')
    if not rows:
        return StepResult(step.label, step.expect_outputs, (), False, 'no SERVO_OUTPUT_RAW received'), baseline
    moved = tuple(i + 1 for i in range(OUTPUT_COUNT) if (not watch or (i + 1) in watch) and max(abs(r[i] - baseline[i]) for r in rows) >= MOVED_US)
    ok = ((len(moved) == 1 and moved[0] in step.expect_outputs) if step.discover else moved == tuple(sorted(step.expect_outputs))) and not rejection
    return StepResult(step.label, step.expect_outputs, moved, ok, note), rows[-1]


def check_discovery(steps: List[Step], results: List[StepResult], assigned: Tuple[int, ...] = ()) -> List[StepResult]:
    """For a scripted matrix: every step moved exactly one output, no output moved twice, and every output the vehicle lists as a motor (`assigned`) was covered.
    Returns [] for any other plan."""
    if not steps or not steps[0].discover:
        return []
    seen = [r.moved[0] for r in results if len(r.moved) == 1]
    ok = bool(results) and len(seen) == len(results) and len(set(seen)) == len(seen) and set(assigned) <= set(seen)
    return [StepResult('each step moved one new output, all assigned motors covered', tuple(sorted(assigned)), tuple(sorted(set(seen))), ok,
                       '%d motors found, order observed: %s' % (len(seen), ' '.join(map(str, seen))))]


def run_motor_test(link, info: VehicleInfo, params: Mapping[str, float], throttle_percent: float = 10.0, arm: bool = False) -> List[StepResult]:
    """Run the planned steps. A Sub needs to be armed; pass arm=True to force-arm it (simulator only) and disarm afterwards."""
    from pymavlink import mavutil
    link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 50000, 0, 0, 0, 0, 0)
    _STATE[:] = [0] * OUTPUT_COUNT
    steps = plan(info, params, throttle_percent)
    needs_armed = any(s.needs_armed for s in steps)
    if needs_armed and not arm:
        raise RuntimeError('this vehicle must be armed for a motor test; pass arm=True to force-arm a simulator')
    if needs_armed:
        link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
    baseline = (_drain(link, 3.0) or [[0] * OUTPUT_COUNT])[-1]
    watch = () if steps and steps[0].discover else monitored_outputs(params)
    results = []
    for step in steps:
        result, baseline = run_step(link, step, baseline, watch)
        if step.discover and results and not result.moved and not result.note.startswith('rejected'):
            break                                            # past the last motor of the scripted matrix
        results.append(result)
    results.extend(check_discovery(steps, results, tuple(sorted(servo_of_motor(params).values()))))
    if needs_armed:
        link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 21196, 0, 0, 0, 0, 0)
    return results


def inspect(port: int, host: str = '127.0.0.1'):
    link, mav_type = connect(port, host)
    params = read_params(link)
    return link, params, detect(params, mav_type)
