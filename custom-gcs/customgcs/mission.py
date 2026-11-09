"""Mission items: check, read and write QGC WPL files, upload, download, verify and clear over MAVLink.

Two facts from the traces shape this module:
- Mission-File-Trace.md: a waypoint with a NaN latitude uploaded as a floating-point MISSION_ITEM made a simulator abort with a floating point exception, while the integer
  form was refused with an error acknowledgement. So items are checked here before anything is sent and are uploaded only as MISSION_ITEM_INT.
- The original Mission Planner file reader skips rows with fewer than ten fields without saying so; this reader rejects them with the line number instead.

Sequence 0 is the home position. A Copter replaces item 0 with its own home, so verify() compares from item 1. Simulator use only so far.
"""
import math
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

GLOBAL_FRAMES = (0, 3, 5, 6, 10, 11)      # MAV_FRAME_GLOBAL, _RELATIVE_ALT, _INT variants, _TERRAIN_ALT: x and y are latitude and longitude in degrees
WPL_HEADER = 'QGC WPL 110'
MISSION, FENCE, RALLY = 0, 1, 2          # MAV_MISSION_TYPE: the mission, the geofence, the rally points
FENCE_POLYGON_INCLUSION = 5001           # MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION: param1 is the number of vertices of this polygon
FENCE_CIRCLE_INCLUSION = 5003            # param1 is the radius in metres
RALLY_POINT = 5100
ACK_ACCEPTED = 0


@dataclass(frozen=True)
class Item:
    seq: int
    frame: int
    command: int
    current: int
    autocontinue: int
    param1: float
    param2: float
    param3: float
    param4: float
    x: float          # latitude (degrees) for global frames
    y: float          # longitude (degrees) for global frames
    z: float          # altitude (metres)


def check(item: Item) -> None:
    """Raise ValueError if the item must not be sent."""
    for name in ('param1', 'param2', 'param3', 'param4', 'x', 'y', 'z'):
        value = getattr(item, name)
        if math.isnan(value) or math.isinf(value):
            raise ValueError('item %d: %s is not a finite number' % (item.seq, name))
    if item.frame in GLOBAL_FRAMES and (item.x != 0 or item.y != 0):
        if not -90.0 <= item.x <= 90.0:
            raise ValueError('item %d: latitude %s is outside -90..90' % (item.seq, item.x))
        if not -180.0 <= item.y <= 180.0:
            raise ValueError('item %d: longitude %s is outside -180..180' % (item.seq, item.y))
    if not 0 <= item.seq < 65535:
        raise ValueError('item %d: sequence out of range' % item.seq)


def check_all(items: Sequence[Item]) -> None:
    for expected, item in enumerate(items):
        check(item)
        if item.seq != expected:
            raise ValueError('item at position %d has sequence %d (sequences must be 0, 1, 2, ...)' % (expected, item.seq))


def dumps_wpl(items: Sequence[Item]) -> str:
    check_all(items)
    rows = [WPL_HEADER]
    for i in items:
        rows.append('\t'.join([str(i.seq), str(i.current), str(i.frame), str(i.command), repr(float(i.param1)), repr(float(i.param2)), repr(float(i.param3)), repr(float(i.param4)),
                               '%.8f' % i.x, '%.8f' % i.y, repr(float(i.z)), str(i.autocontinue)]))
    return '\n'.join(rows) + '\n'


def loads_wpl(text: str) -> List[Item]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith('QGC WPL'):
        raise ValueError('not a QGC WPL file (first line %r)' % (lines[0] if lines else ''))
    items = []
    for number, raw in enumerate(lines[1:], 2):
        if raw.lstrip().startswith('#'):
            continue
        f = raw.replace(',', '\t').split() if '\t' not in raw else raw.split('\t')
        if len(f) != 12:
            raise ValueError('line %d: expected 12 fields, found %d' % (number, len(f)))
        try:
            items.append(Item(int(f[0]), int(f[2]), int(f[3]), int(f[1]), int(f[11]), float(f[4]), float(f[5]), float(f[6]), float(f[7]), float(f[8]), float(f[9]), float(f[10])))
        except ValueError as e:
            raise ValueError('line %d: %s' % (number, e)) from None
    check_all(items)
    return items


def _to_int_fields(item: Item):
    return int(round(item.x * 1e7)), int(round(item.y * 1e7))


def upload(link, items: Sequence[Item], timeout: float = 30.0, mission_type: int = MISSION) -> int:
    """Upload a mission (item 0 is home; a geofence or rally list has no home item). Returns the MISSION_ACK type (0 = accepted). Items are checked first and sent only as MISSION_ITEM_INT."""
    check_all(items)
    if not items:
        raise ValueError('nothing to upload; use clear() to empty the mission')
    link.mav.mission_count_send(link.target_system, link.target_component, len(items), mission_type)
    end = time.time() + timeout
    while time.time() < end:
        msg = link.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'], blocking=True, timeout=1)
        if msg is None:
            continue
        if getattr(msg, 'mission_type', mission_type) != mission_type:
            continue
        if msg.get_type() == 'MISSION_ACK':
            return msg.type
        if msg.seq >= len(items):
            continue
        i = items[msg.seq]
        lat, lon = _to_int_fields(i)
        link.mav.mission_item_int_send(link.target_system, link.target_component, i.seq, i.frame, i.command, i.current, i.autocontinue, i.param1, i.param2, i.param3, i.param4, lat, lon, i.z, mission_type)
    raise TimeoutError('mission upload did not finish within %.0f s' % timeout)


def download(link, timeout: float = 30.0, mission_type: int = MISSION) -> List[Item]:
    link.mav.mission_request_list_send(link.target_system, link.target_component, mission_type)
    end = time.time() + timeout
    count: Optional[int] = None
    items: List[Item] = []
    while time.time() < end:
        if count is None:
            msg = link.recv_match(type='MISSION_COUNT', blocking=True, timeout=1)
            if msg is None or getattr(msg, 'mission_type', mission_type) != mission_type:
                continue
            count = msg.count
            if count:
                link.mav.mission_request_int_send(link.target_system, link.target_component, 0, mission_type)
            continue
        if len(items) == count:
            break
        msg = link.recv_match(type='MISSION_ITEM_INT', blocking=True, timeout=1)
        if msg is not None and getattr(msg, 'mission_type', mission_type) != mission_type:
            continue
        if msg is None:
            link.mav.mission_request_int_send(link.target_system, link.target_component, len(items), mission_type)
            continue
        if msg.seq != len(items):
            continue
        items.append(Item(msg.seq, msg.frame, msg.command, msg.current, msg.autocontinue, msg.param1, msg.param2, msg.param3, msg.param4, msg.x / 1e7, msg.y / 1e7, msg.z))
        if len(items) < count:
            link.mav.mission_request_int_send(link.target_system, link.target_component, len(items), mission_type)
    if count is None or len(items) != count:
        raise TimeoutError('mission download incomplete (%s of %s items)' % (len(items), count))
    link.mav.mission_ack_send(link.target_system, link.target_component, ACK_ACCEPTED, mission_type)
    return items


def clear(link, timeout: float = 10.0, mission_type: int = MISSION) -> int:
    link.mav.mission_clear_all_send(link.target_system, link.target_component, mission_type)
    msg = link.recv_match(type='MISSION_ACK', blocking=True, timeout=timeout)
    if msg is None:
        raise TimeoutError('no acknowledgement of the mission clear')
    return msg.type


def verify(sent: Sequence[Item], received: Sequence[Item], angle_tolerance: float = 1.5e-7, other_tolerance: float = 1e-3, skip_home: bool = True) -> List[str]:
    """Differences between what was uploaded and what the vehicle returns, from item 1 (item 0 is the vehicle's own home). Empty list = same."""
    problems = []
    if len(sent) != len(received):
        problems.append('item count %d sent, %d returned' % (len(sent), len(received)))
    first = 1 if skip_home else 0
    for a, b in zip(sent[first:], received[first:]):
        no_location = a.x == 0 and a.y == 0 and a.z == 0       # the simulator returns frame 0 for such an item (RTL sent with frame 3), so the frame says nothing there
        for name, tol in (('frame', 0 if not no_location else 99), ('command', 0), ('autocontinue', 0), ('param1', other_tolerance), ('param2', other_tolerance), ('param3', other_tolerance), ('param4', other_tolerance),
                          ('x', angle_tolerance), ('y', angle_tolerance), ('z', other_tolerance)):
            if abs(getattr(a, name) - getattr(b, name)) > tol:
                problems.append('item %d %s: sent %r, returned %r' % (a.seq, name, getattr(a, name), getattr(b, name)))
    return problems


def fence_polygon(vertices: Sequence[tuple]) -> List[Item]:
    """Items for one inclusion polygon (frame 0, command 5001, param1 = vertex count). Needs at least three vertices."""
    if len(vertices) < 3:
        raise ValueError('a fence polygon needs at least three vertices')
    return [Item(n, 0, FENCE_POLYGON_INCLUSION, 0, 0, float(len(vertices)), 0.0, 0.0, 0.0, lat, lon, 0.0) for n, (lat, lon) in enumerate(vertices)]


def rally_points(points: Sequence[tuple]) -> List[Item]:
    """Items for rally points given as (lat, lon, altitude above home in metres)."""
    return [Item(n, 3, RALLY_POINT, 0, 0, 0.0, 0.0, 0.0, 0.0, lat, lon, alt) for n, (lat, lon, alt) in enumerate(points)]
