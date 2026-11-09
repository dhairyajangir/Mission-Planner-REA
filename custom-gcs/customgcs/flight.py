"""Arm, disarm and flight modes for a Copter, with the vehicle's own refusal reasons.

The mode table is generated from ArduCopter/mode.h (tools/gen_copter_modes.py, data/copter_modes.json). Every command reports the COMMAND_ACK result and the STATUSTEXT
lines the vehicle sent while it was handled: the simulator reports "Arm: Accels inconsistent" style reasons and mode refusals only as text. Simulator use only so far.
"""
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

MAV_CMD_DO_SET_MODE = 176
MAV_CMD_COMPONENT_ARM_DISARM = 400
FORCE_MAGIC = 21196          # param2 of MAV_CMD_COMPONENT_ARM_DISARM: skip the arming checks. Never sent unless force=True.


@dataclass(frozen=True)
class Result:
    ok: bool
    detail: str
    texts: tuple = ()


def copter_modes() -> Dict[str, int]:
    """{name: number} for the modes that can be requested (AUTO_RTL is not a true mode and is left out)."""
    with open(os.path.join(os.path.dirname(__file__), 'data', 'copter_modes.json'), encoding='utf-8') as f:
        return {k: v['number'] for k, v in json.load(f)['modes'].items() if v['settable']}


def mode_name(number: int) -> str:
    with open(os.path.join(os.path.dirname(__file__), 'data', 'copter_modes.json'), encoding='utf-8') as f:
        for k, v in json.load(f)['modes'].items():
            if v['number'] == number:
                return k
    return 'UNKNOWN(%d)' % number


def is_armed(heartbeat) -> bool:
    return bool(heartbeat.base_mode & 128)           # MAV_MODE_FLAG_SAFETY_ARMED


def _vehicle_heartbeat(msg) -> bool:
    return msg.get_type() == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27)       # not a ground station or ADSB heartbeat


def _wait(link, seconds: float, until=None):
    """Collect (heartbeat, ack results, texts) for up to `seconds` or until until(heartbeat) is true."""
    texts: List[str] = []
    acks: List[int] = []
    last = None
    end = time.time() + seconds
    while time.time() < end:
        msg = link.recv_match(type=['HEARTBEAT', 'COMMAND_ACK', 'STATUSTEXT'], blocking=True, timeout=0.3)
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == 'HEARTBEAT' and _vehicle_heartbeat(msg):
            last = msg
            if until is not None and until(msg):
                break
        elif kind == 'COMMAND_ACK':
            acks.append(msg.result)
        elif kind == 'STATUSTEXT':
            texts.append(msg.text)
    return last, acks, texts


def current_heartbeat(link, timeout: float = 5.0):
    hb, _, _ = _wait(link, timeout, until=lambda h: True)
    return hb


def current_mode(link) -> Optional[str]:
    hb = current_heartbeat(link)
    return None if hb is None else mode_name(hb.custom_mode)


def _arm_command(link, arm: bool, force: bool) -> None:
    link.mav.command_long_send(link.target_system, link.target_component, MAV_CMD_COMPONENT_ARM_DISARM, 0, 1 if arm else 0, FORCE_MAGIC if force else 0, 0, 0, 0, 0, 0)


def arm(link, force: bool = False, timeout: float = 60.0) -> Result:
    """Ask the vehicle to arm and wait until a heartbeat says it is. A refusal is retried every few seconds until `timeout` because the checks pass only some time after start-up;
    the reasons the vehicle gave are returned with the result."""
    end = time.time() + timeout
    texts: List[str] = []
    ack = None
    while time.time() < end:
        _arm_command(link, True, force)
        hb, acks, new = _wait(link, 4.0, until=is_armed)
        texts += new
        if acks:
            ack = acks[-1]
        if hb is not None and is_armed(hb):
            return Result(True, 'armed (ack result %s)' % ack, tuple(texts))
    return Result(False, 'not armed after %.0f s (last ack result %s)' % (timeout, ack), tuple(dict.fromkeys(texts)))


def disarm(link, force: bool = False, timeout: float = 15.0) -> Result:
    _arm_command(link, False, force)
    hb, acks, texts = _wait(link, timeout, until=lambda h: not is_armed(h))
    ok = hb is not None and not is_armed(hb)
    return Result(ok, ('disarmed' if ok else 'still armed') + (' (ack result %s)' % acks[-1] if acks else ''), tuple(texts))


def set_mode(link, name: str, timeout: float = 5.0) -> Result:
    """Request a flight mode by name and wait for a heartbeat that reports it. Unknown names raise KeyError before anything is sent."""
    number = copter_modes()[name.upper()]
    link.mav.command_long_send(link.target_system, link.target_component, MAV_CMD_DO_SET_MODE, 0, 1, number, 0, 0, 0, 0, 0)
    hb, acks, texts = _wait(link, timeout, until=lambda h: h.custom_mode == number)
    ok = hb is not None and hb.custom_mode == number
    reported = mode_name(hb.custom_mode) if hb is not None else 'no heartbeat'
    return Result(ok, ('%s active' % name.upper()) if ok else ('%s refused: vehicle stays in %s (ack result %s)' % (name.upper(), reported, acks[-1] if acks else 'none')), tuple(texts))
