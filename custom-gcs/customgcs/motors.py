"""Plan a motor test that is correct for the connected vehicle, and say which servo output should move for each step.

Rules, each recorded with evidence in the traces:
- Copter and QuadPlane (Copter-/Plane-Frame-Types-Trace.md): param1 is a test sequence 1..N; the firmware's testing order maps a sequence to a motor, and the motor is on the
  servo output whose SERVOn_FUNCTION is the motor function (motor 1 is output 1 on a Copter, often output 5 on a QuadPlane). The vehicle must be disarmed.
- Sub (Sub-Frame-Types-Trace.md): board-order test, param1 is a zero-based output, the vehicle must be armed and the command repeated within 500 ms.
- Rover (Rover-Frame-Types-Trace.md): param1 1 throttle, 2 steering, 3 throttle left, 4 throttle right, on the outputs with the matching servo function; no main sail.
"""
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from .vehicle import VehicleInfo

_LAYOUTS = None


class Unsupported(Exception):
    """No motor test plan is known for this vehicle or frame."""


@dataclass(frozen=True)
class Step:
    label: str
    params: Tuple[float, ...]                # param1..param7 of MAV_CMD_DO_MOTOR_TEST
    expect_outputs: Tuple[int, ...]          # servo outputs (1 based) that should move
    needs_armed: bool = False
    needs_disarmed: bool = False
    repeat_every_s: Optional[float] = None
    discover: bool = False                   # scripted matrix: the order is defined by a Lua script the ground station cannot see; expect_outputs is then the set of motor outputs and each step must move exactly one of them


def layouts() -> Mapping[str, list]:
    global _LAYOUTS
    if _LAYOUTS is None:
        with open(os.path.join(os.path.dirname(__file__), 'data', 'matrix_layouts.json'), encoding='utf-8') as f:
            _LAYOUTS = json.load(f)['layouts']
    return _LAYOUTS


def motor_number(function: int) -> Optional[int]:
    """Motor number for a SERVOn_FUNCTION value (33..40 motors 1..8, 82..85 motors 9..12, 160..179 motors 13..32)."""
    if 33 <= function <= 40:
        return function - 32
    if 82 <= function <= 85:
        return function - 73
    if 160 <= function <= 179:
        return function - 147
    return None


def servo_functions(params: Mapping[str, float]) -> Dict[int, int]:
    return {n: int(params['SERVO%d_FUNCTION' % n]) for n in range(1, 33) if 'SERVO%d_FUNCTION' % n in params}


def servo_of_motor(params: Mapping[str, float]) -> Dict[int, int]:
    result: Dict[int, int] = {}
    for servo, function in sorted(servo_functions(params).items()):
        number = motor_number(function)
        if number is not None and number not in result:
            result[number] = servo
    return result


# Single (8) and coax (9) copters have no generated table. Transcribed by hand from _output_test_seq in AP_MotorsSingle.cpp and AP_MotorsCoax.cpp: sequences 1 to 4 are the
# four flap servos (Motor1..4 functions, idle 1500, driven down by a test), 5 and 6 the two motors; confirmed 6 of 6 in the simulator (Copter-Frame-Types-Trace.md).
_HAND = {'8': [{'order': n, 'number': n, 'rotation': 'flap servo' if n <= 4 else 'motor'} for n in range(1, 7)],
         '9': [{'order': n, 'number': n, 'rotation': 'flap servo' if n <= 4 else 'motor'} for n in range(1, 7)]}


def _layout(info: VehicleInfo) -> list:
    table = layouts()
    if str(info.frame_class) in _HAND:
        return _HAND[str(info.frame_class)]
    for key in ('%s:%s' % (info.frame_class, info.frame_type), '%s:default' % info.frame_class):
        if key in table:
            return table[key]
    raise Unsupported('no motor layout for frame class %s type %s (scripted matrices need their Lua script)' % (info.frame_class, info.frame_type))


# MOTOR_FRAME_TYPE_NYT_PLUS (16) and NYT_X (17) exist only in ArduPlane (and unknown) builds of AP_MotorsMatrix (#if APM_BUILD_TYPE(APM_BUILD_ArduPlane) ...). A Copter
# with class 1 and one of those types is not initialised and refuses the motor test with "Motor Test: Check frame class and type" (sitl-evidence/custom-gcs-all-layouts/).
_PLANE_ONLY_TYPES = {(1, 16), (1, 17)}
# Scripting matrix classes (15 and 17): the test order comes from add_motor(..., testing_order) calls in a Lua script on the vehicle. The ground station cannot read that script, so it
# plans up to 32 sequences, stops at the first that moves nothing, and checks that every step moved exactly one output, no output twice, and every output the vehicle lists as a motor was covered (link.check_discovery).
_SCRIPTED_CLASSES = (15, 17)


def plan(info: VehicleInfo, params: Mapping[str, float], throttle_percent: float = 10.0, seconds: float = 1.0) -> List[Step]:
    if info.kind == 'copter' and (info.frame_class, info.frame_type) in _PLANE_ONLY_TYPES:
        raise Unsupported('frame class %s type %s (NYT) is compiled only into ArduPlane builds; a Copter refuses the motor test ("Check frame class and type")' % (info.frame_class, info.frame_type))
    if info.kind == 'copter' and info.frame_class in _SCRIPTED_CLASSES:
        if not servo_of_motor(params):
            raise Unsupported('scripted matrix frame without any motor output assigned (is the Lua script running?)')
        # SERVOn_FUNCTION parameters exist only for outputs 1..16 here, so the true motor count cannot be read: plan 32 sequences; the runner stops at the first one that moves nothing.
        return [Step('sequence %d: whichever motor the script assigns' % n, (float(n), 0.0, throttle_percent, seconds, 1.0, 1.0, 0.0), tuple(range(1, 33)), needs_disarmed=True, discover=True)
                for n in range(1, 33)]
    if info.kind in ('copter', 'quadplane'):
        outputs = servo_of_motor(params)
        steps = []
        for motor in sorted(_layout(info), key=lambda m: m['order']):
            servo = outputs.get(motor['number'])
            steps.append(Step('sequence %d: motor %d (%s)' % (motor['order'], motor['number'], motor['rotation']),
                              (float(motor['order']), 0.0, throttle_percent, seconds, 1.0, 1.0, 0.0), (servo,) if servo else (), needs_disarmed=True))
        return steps
    if info.kind == 'sub':
        return [Step('output %d (zero-based %d)' % (servo, servo - 1), (float(servo - 1), 0.0, throttle_percent, seconds, 1.0, 2.0, 0.0), (servo,), needs_armed=True, repeat_every_s=0.25)
                for _, servo in sorted(servo_of_motor(params).items(), key=lambda kv: kv[1])]
    if info.kind == 'rover':
        functions = servo_functions(params)
        wanted = {1: (70, 33), 2: (26, 34), 3: (73, 35), 4: (74, 36)}
        names = {1: 'throttle', 2: 'steering', 3: 'throttle left', 4: 'throttle right'}
        return [Step(names[k], (float(k), 0.0, 50.0, 2.0, 0.0, 0.0, 0.0), tuple(s for s, f in sorted(functions.items()) if f in wanted[k])) for k in sorted(wanted)]
    if info.kind == 'heli':
        raise Unsupported('helicopters have no motor test: the firmware answers MAV_CMD_DO_MOTOR_TEST with "Motor Test: Disabled on heli" (sitl-evidence/heli-motor-test-probe/)')
    raise Unsupported('no motor test plan for a %s' % info.kind)
