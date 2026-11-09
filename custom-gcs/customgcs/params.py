"""Parameter files, diff and restore for an ArduPilot vehicle.

Facts this relies on (Setup-Page-Disabled-Reasons-Trace.md): reading single parameter names was unreliable on the simulators, so the whole list is downloaded once
(link.read_params); parameters are 32-bit floats on the wire, so comparisons are made after rounding to float32.

Writing parameters changes the vehicle. restore() refuses an armed vehicle, never touches the parameters in PROTECTED (serial/link settings, counters) unless asked, and
re-downloads the list afterwards to report what still differs. Simulator use only so far.
"""
import math
import re
import struct
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

# Not restored by default: changing a serial port or system id can cut the link that restore itself uses; STAT_* are counters; the rest are values the vehicle updates itself
# (seen in sitl-evidence/custom-gcs-cli-smoke-run1-*: the ground pressure of each barometer and the compass declination changed within a minute, MIS_TOTAL follows the mission,
# and the vehicle refused to take the old BARO and MIS_TOTAL values back).
PROTECTED_PREFIXES = ('SERIAL', 'STAT_')
VOLATILE_PATTERN = re.compile(r'^(COMPASS_DEC|MIS_TOTAL|BARO\d*_GND_(PRESS|TEMP))$')
MAV_PARAM_TYPE_REAL32 = 9
PROTECTED_NAMES = ('SYSID_THISMAV', 'FORMAT_VERSION', 'CMD_TOTAL', 'CMD_INDEX')


def f32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', float(value)))[0]


def same(a: float, b: float) -> bool:
    a, b = f32(a), f32(b)
    return (math.isnan(a) and math.isnan(b)) or a == b


def volatile(name: str) -> bool:
    """True for parameters the vehicle keeps updating itself; a difference there is not a setting that changed."""
    return bool(VOLATILE_PATTERN.match(name))


def protected(name: str) -> bool:
    return name in PROTECTED_NAMES or name.startswith(PROTECTED_PREFIXES) or volatile(name)


@dataclass(frozen=True)
class Change:
    name: str
    old: Optional[float]          # None: the vehicle does not have this parameter
    new: float


def diff(current: Mapping[str, float], wanted: Mapping[str, float]) -> List[Change]:
    """Parameters in `wanted` whose value differs from `current` (or that `current` lacks), sorted by name."""
    return [Change(n, current.get(n), v) for n, v in sorted(wanted.items()) if n not in current or not same(current[n], v)]


def dumps(params: Mapping[str, float], title: str = '') -> str:
    lines = ['# customgcs parameter file: NAME,VALUE' + (' (' + title + ')' if title else '')]
    lines += ['%s,%s' % (n, '%.9g' % f32(v)) for n, v in sorted(params.items())]      # 9 significant digits round-trip a float32
    return '\n'.join(lines) + '\n'


def loads(text: str) -> Dict[str, float]:
    """Parse `NAME,VALUE`, `NAME VALUE` or `NAME<TAB>VALUE` lines; '#' starts a comment. Raises ValueError with the line number on anything else, NaN or infinity."""
    result: Dict[str, float] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = line.replace(',', ' ').replace('\t', ' ').split()
        if len(parts) != 2:
            raise ValueError('line %d: expected NAME,VALUE, got %r' % (number, raw))
        try:
            value = float(parts[1])
        except ValueError:
            raise ValueError('line %d: %r is not a number' % (number, parts[1])) from None
        if math.isnan(value) or math.isinf(value):
            raise ValueError('line %d: %s has a non-finite value' % (number, parts[0]))
        if parts[0] in result:
            raise ValueError('line %d: %s appears twice' % (number, parts[0]))
        result[parts[0]] = value
    return result


@dataclass(frozen=True)
class WriteResult:
    name: str
    wanted: float
    got: Optional[float]
    ok: bool
    note: str = ''


def write(link, changes: Iterable[Change], timeout: float = 3.0, tries: int = 3) -> List[WriteResult]:
    """Set each parameter and wait for the vehicle's PARAM_VALUE echo of that name."""
    results = []
    for change in changes:
        got = None
        for _ in range(tries):
            link.mav.param_set_send(link.target_system, link.target_component, change.name.encode(), float(change.new), MAV_PARAM_TYPE_REAL32)
            end = time.time() + timeout
            while time.time() < end:
                msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
                if msg is not None and msg.param_id.rstrip('\x00') == change.name:
                    got = msg.param_value
                    break
            if got is not None:
                break
        ok = got is not None and same(got, change.new)
        results.append(WriteResult(change.name, change.new, got, ok, '' if ok else ('no echo' if got is None else 'vehicle kept a different value')))
    return results


@dataclass(frozen=True)
class RestoreReport:
    planned: Tuple[Change, ...]
    skipped_protected: Tuple[str, ...]
    results: Tuple[WriteResult, ...]
    remaining: Tuple[Change, ...]        # differences left after re-downloading the list (protected names excluded)


def restore(link, wanted: Mapping[str, float], read_params, armed: bool, include_protected: bool = False, dry_run: bool = False) -> RestoreReport:
    """Bring the vehicle's parameters to `wanted`. `read_params(link)` downloads the full list; `armed` is the vehicle's current armed state (refused when True)."""
    if armed:
        raise RuntimeError('refusing to write parameters while the vehicle is armed')
    current = read_params(link)
    planned = diff(current, wanted)
    skipped = tuple(c.name for c in planned if protected(c.name) and not include_protected)
    todo = [c for c in planned if c.name not in skipped]
    if dry_run:
        return RestoreReport(tuple(todo), skipped, (), tuple(todo))
    results = write(link, todo)
    after = read_params(link)
    remaining = tuple(c for c in diff(after, {n: v for n, v in wanted.items() if include_protected or not protected(n)}))
    return RestoreReport(tuple(todo), skipped, tuple(results), remaining)
