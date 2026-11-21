"""Check selected numeric fields in the retained Mission Planner DataFlash conversion."""
import csv
import hashlib
import json
import math
import struct
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "sitl-evidence/nonempty-log-probe"
SELECTED = {"GPS", "ATT", "BARO", "IMU", "CTUN", "BAT", "RCIN"}
FMT = struct.Struct("<BB4s16s64s")
STORAGE = {"c": "h", "e": "i", "L": "i"}
EXPONENT = {"c": -2, "e": -2, "L": -7}


def field_text(raw):
    return raw.rstrip(b"\0").decode("ascii")


def binary_rows(data):
    lengths = {128: FMT.size + 3}
    selected = {}
    pos = 0
    while pos < len(data):
        if data[pos:pos + 2] != b"\xa3\x95" or pos + 3 > len(data):
            raise ValueError(f"Expected DataFlash header at byte {pos}")
        kind = data[pos + 2]
        end = pos + lengths[kind]
        if end > len(data):
            if kind in selected:
                raise ValueError(f"Incomplete selected record at {pos}")
            break
        if kind == 128:
            number, length, raw_name, raw_codes, raw_cols = FMT.unpack_from(data, pos + 3)
            lengths[number] = length
            name = field_text(raw_name)
            if name in SELECTED:
                codes = field_text(raw_codes)
                cols = field_text(raw_cols).split(",")
                layout = struct.Struct("<" + "".join(STORAGE.get(c, c) for c in codes))
                if len(cols) != len(codes) or layout.size + 3 != length:
                    raise ValueError(f"Inconsistent format for {name}")
                selected[number] = name, codes, cols, layout
        elif kind in selected:
            name, codes, cols, layout = selected[kind]
            yield name, codes, cols, layout.unpack_from(data, pos + 3)
        pos = end


def text_rows(path):
    with path.open(encoding="ascii") as stream:
        for row in csv.reader(stream, skipinitialspace=True):
            if row and row[0] in SELECTED:
                yield row[0], row[1:]


def compare():
    binary = (CAPTURE / "downloaded.bin").read_bytes()
    text_file = CAPTURE / "converted.log"
    counts = defaultdict(lambda: {"records": 0, "exact_fixed": 0, "rounded_float": 0,
                                  "midpoint_away_from_zero": 0, "matched_nan": 0,
                                  "differences": 0})
    examples = []
    text = iter(text_rows(text_file))
    for name, codes, columns, values in binary_rows(binary):
        text_name, fields = next(text)
        if name != text_name or len(fields) != len(columns):
            raise ValueError(f"Sequence or column count differs at {name} {values[0]}")
        out = counts[name]
        out["records"] += 1
        for code, column, raw, token in zip(codes, columns, values, fields):
            actual = Decimal(token)
            if code == "f" and math.isnan(raw) and actual.is_nan():
                out["matched_nan"] += 1
                continue
            # Keep exact midpoints separate to expose the release's observed tie handling.
            if code == "f":
                value = Decimal.from_float(raw)
                step = Decimal(1).scaleb(value.adjusted() - 6)
                expected = value.quantize(step, rounding=ROUND_HALF_UP)
                category = "rounded_float"
                if expected != Decimal(format(raw, ".7g")):
                    category = "midpoint_away_from_zero"
            else:
                expected = Decimal(raw).scaleb(EXPONENT.get(code, 0))
                category = "exact_fixed"
            if expected == actual:
                out[category] += 1
            else:
                out["differences"] += 1
                if len(examples) < 12:
                    examples.append([name, values[0], column, str(expected), token])
    if next(text, None) is not None or set(counts) != SELECTED:
        raise ValueError("Selected record stream incomplete")
    return {"binary_sha256": hashlib.sha256(binary).hexdigest(),
            "text_sha256": hashlib.sha256(text_file.read_bytes()).hexdigest(),
            "message_counts": dict(sorted(counts.items())),
            "first_differences": examples}


if __name__ == "__main__":
    print(json.dumps(compare(), indent=2))
