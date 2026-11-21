"""Exercise the original DataFlash comparator offline, against a recorded plus-frame Copter flight."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CORPUS = ROOT / "sitl-evidence/copter-variants"
SOURCE = CORPUS / "plus-logged-flight-00000001.BIN.gz"
REFERENCE = CORPUS / "plus-sim-truth-accuracy.csv"
COMPARATOR = ROOT / "research-tools/analyze-sim-truth-accuracy.py"
LOG_PIN = "aa2c351f42059566c9499644417005a7cc73a62a0e5ed4f6d30042e265e15803"
SCRIPT_PIN = "990f3020cf5ce4e43451c025fafee97d8704d08c37accab5300c551736bb23a2"
HEADER = b"\xa3\x95"
FORMAT = 128
SIM, POS = 78, 75


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_records(blob):
    """Extract original FMT, SIM and POS records by declared length, never by payload-pattern guessing."""
    lengths = {FORMAT: 89}
    descriptions, records = {}, []
    pos = 0
    while pos < len(blob):
        require(blob[pos:pos + 2] == HEADER, f"Unexpected record at byte {pos}")
        typ = blob[pos + 2]
        length = lengths[typ]
        frame = blob[pos:pos + length]
        if len(frame) != length:
            # The pinned original ends with eight bytes of one 54-byte IMU record.
            require((typ, length, len(frame)) == (166, 54, 8), "Unexpected partial final record")
            break
        if typ == FORMAT:
            declared, size, name, fmt, cols = struct.unpack_from("<BB4s16s64s", frame, 3)
            lengths[declared] = size
            if declared in (FORMAT, SIM, POS):
                descriptions[declared] = frame
                expected = {FORMAT: b"BBnNZ", SIM: b"QccCfLLffff", POS: b"QLLfff"}
                require(fmt.rstrip(b"\0") == expected[declared], f"Unexpected {name} packing")
        elif typ in (SIM, POS):
            records.append(frame)
        pos += length
    return b"".join(descriptions[k] for k in (FORMAT, SIM, POS)), records


def stamp(frame):
    return struct.unpack_from("<Q", frame, 3)[0]


def altitude(frame):
    return struct.unpack_from("<f", frame, 17 if frame[2] == SIM else 19)[0]


def modified(frames, case):
    truth = [f for f in frames if f[2] == SIM]
    cutoff = stamp(truth[0]) + 3 * (stamp(truth[-1]) - stamp(truth[0])) // 4
    for frame in frames:
        if case == "missing_truth_tail" and frame[2] == SIM and stamp(frame) > cutoff:
            continue
        if case == "pos_delayed_1s" and frame[2] == POS:
            frame = frame[:3] + struct.pack("<Q", stamp(frame) + 1_000_000) + frame[11:]
        yield frame


def expected(frames):
    """Linear time merge over two independently decoded altitude streams."""
    truth = [(stamp(f), altitude(f)) for f in frames if f[2] == SIM]
    pos = [(stamp(f), altitude(f)) for f in frames if f[2] == POS]
    require(truth == sorted(truth) and pos == sorted(pos), "Input stream order changed")
    by_part = {"whole log": [], "airborne": []}
    age = []
    beyond = 0
    index = -1
    for tick, alt in pos:
        while index + 1 < len(truth) and truth[index + 1][0] <= tick:
            index += 1
        if index < 0:
            continue
        t, ref = truth[index]
        age.append(tick - t)
        beyond += tick > truth[-1][0]
        err = abs(alt - ref)
        by_part["whole log"].append(err)
        if ref > truth[0][1] + 1.0:
            by_part["airborne"].append(err)
    stats = {}
    for part, errors in by_part.items():
        n = len(errors)
        stats[part] = [n, round(statistics.fmean(errors), 4),
                       round(math.sqrt(statistics.fmean(e * e for e in errors)), 4),
                       round(sorted(errors)[n * 95 // 100], 4), round(max(errors), 4)]
    return {"truth_samples": len(truth), "position_samples": len(pos),
            "last_truth_altitude_m_amsl": truth[-1][1], "position_samples_after_last_truth": beyond,
            "max_matched_truth_age_seconds": max(age) / 1_000_000, "altitude_error_rows": stats}


def rows(text):
    output = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row["estimate"] == "AHRS altitude (POS)":
            output[row["part"]] = [int(row["n"]), *[float(row[k]) for k in ("mean_abs", "rms", "p95", "max")]]
    return output


def replay():
    from pymavlink import __version__
    compressed = SOURCE.read_bytes()
    require(hashlib.sha256(compressed).hexdigest() == LOG_PIN, "Archived flight differs")
    script_hash = hashlib.sha256(COMPARATOR.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    require(script_hash == SCRIPT_PIN, "Comparator differs")
    formats, original = read_records(gzip.decompress(compressed))
    result = {"archive_sha256": LOG_PIN, "comparator_sha256_lf": script_hash, "pymavlink": __version__, "cases": {}}
    with tempfile.TemporaryDirectory(dir=HERE) as scratch:
        work = Path(scratch)
        env = dict(os.environ, TMPDIR=scratch, TEMP=scratch, TMP=scratch, PYTHONDONTWRITEBYTECODE="1")
        for case in ("archived_control", "pos_delayed_1s", "missing_truth_tail"):
            frames = list(modified(original, case))
            path = work / (case + ".BIN.gz")
            path.write_bytes(gzip.compress(formats + b"".join(frames), mtime=0))
            out = work / (case + ".csv")
            subprocess.run([sys.executable, "-B", str(COMPARATOR), scratch, str(out), path.name],
                           cwd=scratch, env=env, check=True, capture_output=True, text=True)
            observed = rows(out.read_text())
            wanted = expected(frames)
            require(observed == wanted["altitude_error_rows"], f"Independent check failed: {case}")
            if case == "archived_control":
                require(observed == rows(REFERENCE.read_text()), "Projected control differs from published flight results")
            result["cases"][case] = wanted
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = replay()
    path = HERE / "results.json"
    if args.check:
        require(json.loads(path.read_text()) == result, "Unexpected replay result")
    else:
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["cases"], indent=2))
