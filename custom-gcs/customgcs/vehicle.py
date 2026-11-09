"""Work out what kind of vehicle is connected and how its frame is described, from its parameters and heartbeat type.

The evidence behind the rules is in Copter-, Sub-, Rover-, Plane- and Blimp-Frame-Types-Trace.md: the frame parameters differ by firmware
(FRAME_CLASS/FRAME_TYPE, Q_FRAME_CLASS/Q_FRAME_TYPE for a QuadPlane, FRAME_CONFIG for Sub).
"""
from dataclasses import dataclass
from typing import Mapping, Optional

MAV_FIXED_WING, MAV_HELICOPTER, MAV_TRACKER, MAV_AIRSHIP, MAV_ROVER, MAV_BOAT, MAV_SUBMARINE = 1, 4, 5, 7, 10, 11, 12
HELI_CLASSES = (6, 11, 13)          # MOTOR_FRAME_HELI, HELI_DUAL, HELI_QUAD


@dataclass(frozen=True)
class VehicleInfo:
    kind: str                        # copter, heli, quadplane, plane, sub, rover, blimp, tracker
    frame_class: Optional[int]
    frame_type: Optional[int]
    class_param: Optional[str]
    type_param: Optional[str]


def _value(params: Mapping[str, float], name: str) -> Optional[int]:
    return int(params[name]) if name in params else None


def detect(params: Mapping[str, float], mav_type: int) -> VehicleInfo:
    """params: the vehicle's full parameter list (name to value); mav_type: the MAV_TYPE of its heartbeat."""
    if mav_type == MAV_SUBMARINE or 'FRAME_CONFIG' in params:
        return VehicleInfo('sub', _value(params, 'FRAME_CONFIG'), None, 'FRAME_CONFIG', None)
    if mav_type in (MAV_ROVER, MAV_BOAT):
        return VehicleInfo('rover', _value(params, 'FRAME_CLASS'), _value(params, 'FRAME_TYPE'), 'FRAME_CLASS', 'FRAME_TYPE')
    if mav_type == MAV_AIRSHIP:
        return VehicleInfo('blimp', _value(params, 'FRAME_CLASS'), None, 'FRAME_CLASS', None)
    if mav_type == MAV_TRACKER:
        return VehicleInfo('tracker', None, None, None, None)
    if mav_type == MAV_FIXED_WING or 'Q_ENABLE' in params:
        if params.get('Q_ENABLE', 0) and 'Q_FRAME_CLASS' in params:
            return VehicleInfo('quadplane', _value(params, 'Q_FRAME_CLASS'), _value(params, 'Q_FRAME_TYPE'), 'Q_FRAME_CLASS', 'Q_FRAME_TYPE')
        return VehicleInfo('plane', None, None, None, None)
    cls = _value(params, 'FRAME_CLASS')
    if mav_type == MAV_HELICOPTER or cls in HELI_CLASSES:
        return VehicleInfo('heli', cls, _value(params, 'FRAME_TYPE'), 'FRAME_CLASS', 'FRAME_TYPE')
    return VehicleInfo('copter', cls, _value(params, 'FRAME_TYPE'), 'FRAME_CLASS', 'FRAME_TYPE')
