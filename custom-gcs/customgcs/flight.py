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
MAV_CMD_MISSION_START = 300
FORCE_MAGIC = 21196          # param2 of MAV_CMD_COMPONENT_ARM_DISARM: skip the arming checks. Never sent unless force=True.


@dataclass(frozen=True)
class Result:
    ok: bool
    detail: str
    texts: tuple = ()


MODE_FILES = {'copter': 'copter_modes.json', 'rover': 'rover_modes.json', 'plane': 'plane_modes.json'}
TABLE_FOR_KIND = {'copter': 'copter', 'heli': 'copter', 'rover': 'rover', 'plane': 'plane', 'quadplane': 'plane'}          # a Copter helicopter build uses the Copter mode table (it adds AUTOROTATE, which is already in it)


def _table(table: str) -> dict:
    if table not in MODE_FILES:
        raise KeyError('no flight mode table for %r (have: %s)' % (table, ', '.join(sorted(MODE_FILES))))
    with open(os.path.join(os.path.dirname(__file__), 'data', MODE_FILES[table]), encoding='utf-8') as f:
        return json.load(f)['modes']


def table_for(kind: str) -> str:
    if kind not in TABLE_FOR_KIND:
        raise KeyError('flight modes are only implemented for %s, not for a %s' % (', '.join(sorted(TABLE_FOR_KIND)), kind))
    return TABLE_FOR_KIND[kind]


def vehicle_modes(table: str = 'copter') -> Dict[str, int]:
    """{name: number} for the modes that can be requested (entries flagged not settable, such as Copter AUTO_RTL and Rover INITIALISING, are left out)."""
    return {k: v['number'] for k, v in _table(table).items() if v['settable']}


def copter_modes() -> Dict[str, int]:
    return vehicle_modes('copter')


def mode_name(number: int, table: str = 'copter') -> str:
    for k, v in _table(table).items():
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


def current_mode(link, table: str = 'copter') -> Optional[str]:
    hb = current_heartbeat(link)
    return None if hb is None else mode_name(hb.custom_mode, table)


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


def set_mode(link, name: str, timeout: float = 5.0, table: str = 'copter') -> Result:
    """Request a flight mode by name and wait for a heartbeat that reports it. Unknown names raise KeyError before anything is sent. `table` picks the vehicle's mode table ('copter', 'rover' or 'plane'; see table_for). Mode numbers mean different things per vehicle (4 is GUIDED on a Copter, HOLD on a Rover, ACRO on a Plane)."""
    number = vehicle_modes(table)[name.upper()]
    link.mav.command_long_send(link.target_system, link.target_component, MAV_CMD_DO_SET_MODE, 0, 1, number, 0, 0, 0, 0, 0)
    hb, acks, texts = _wait(link, timeout, until=lambda h: h.custom_mode == number)
    ok = hb is not None and hb.custom_mode == number
    reported = mode_name(hb.custom_mode, table) if hb is not None else 'no heartbeat'
    return Result(ok, ('%s active' % name.upper()) if ok else ('%s refused: vehicle stays in %s (ack result %s)' % (name.upper(), reported, acks[-1] if acks else 'none')), tuple(texts))


def start_mission(link, timeout: float = 5.0) -> Result:
    """Send MAV_CMD_MISSION_START. A Copter that is armed in AUTO on the ground does not take off until the mission is started (or the pilot raises the throttle) and disarms itself
    after DISARM_DELAY (10 s) if neither happens (sitl-evidence/custom-gcs-flight-run3-* and -run4-*)."""
    link.mav.command_long_send(link.target_system, link.target_component, MAV_CMD_MISSION_START, 0, 0, 0, 0, 0, 0, 0, 0)
    _, acks, texts = _wait(link, timeout, until=None)
    ok = bool(acks) and acks[-1] == 0
    return Result(ok, 'mission start %s (ack result %s)' % ('accepted' if ok else 'not accepted', acks[-1] if acks else 'none'), tuple(texts))
