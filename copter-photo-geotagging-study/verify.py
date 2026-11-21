"""Replay original release EXIF matching and compare tagged JPEG with independent survey data."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARCHIVE_SHA = "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9"
INPUTS = HERE / "inputs"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def jpeg(path):
    with Image.open(path) as photo:
        exif = photo.getexif()
        camera = exif.get_ifd(0x8769)
        gps = exif.get_ifd(0x8825)
        result = {"date_taken": camera.get(0x9003), "digitized": camera.get(0x9004),
                  "size": list(photo.size), "pixels_sha256": digest(photo.convert("RGB").tobytes())}
        if gps:
            def degree(dms, direction):
                d,m,s = map(float, dms)
                return (d + m/60 + s/3600) * (-1 if direction in ("W","S") else 1)
            result["gps"] = [degree(gps[2],gps[1]),degree(gps[4],gps[3]),float(gps[6])]
        return result

def expected():
    raw = (INPUTS / "survey.tlog").read_bytes()
    nominal = jpeg(INPUTS / "nominal.jpg")
    missing = jpeg(INPUTS / "missing-time.jpg")
    assert nominal["pixels_sha256"] == missing["pixels_sha256"]
    assert nominal["date_taken"] == "2024:06:15 17:30:00" and missing["date_taken"] is None
    assert not missing["digitized"] and "gps" not in nominal and "gps" not in missing
    survey_zone = timezone(timedelta(hours=5, minutes=30))
    epoch = datetime.strptime(nominal["date_taken"], "%Y:%m:%d %H:%M:%S").replace(tzinfo=survey_zone).timestamp()
    samples = []
    for i in range(0,len(raw),44):
        stamp, = struct.unpack_from(">Q", raw, i)
        assert raw[i+8:i+10] == b"\xfe\x1c" and raw[i+13] == 33
        lat,lon,alt = struct.unpack_from("<iii",raw,i+18)
        samples.append((abs(stamp/1e6-epoch), [lat/1e7,lon/1e7,alt/1000]))
    assert len(samples) == 3 and min(samples)[0] == 0
    return min(samples)[1]

def check_retained():
    report = json.loads((HERE / "result.json").read_text())
    assert report["expected_fix"] == expected()
    assert report["fixture_sha256"] == {p.name:digest(p.read_bytes()) for p in INPUTS.iterdir()}
    assert report["input"] == {p.name:jpeg(p) for p in INPUTS.glob("*.jpg")}
    output = HERE / "nominal_geotag.jpg"
    assert report["tagged_sha256"] == digest(output.read_bytes())
    assert report["output"] == jpeg(output)
    assert report["output"]["gps"] == expected()
    assert report["output"]["pixels_sha256"] == report["input"]["nominal.jpg"]["pixels_sha256"]
    raw = (HERE / "observation.txt").read_text()
    for marker in ("INITIAL_CACHE 0", "APP Images read : 2", "MATCHES 1", "Photo missing-time NOT PROCESSED",
                   "PHOTO missing-time.jpg 0001-01-01T00:00:00.000 Unspecified", "RESULT nominal.jpg 2024-06-15T17:30:00.000 2024-06-15T17:30:00.000 -35.125 149.25 120"):
        assert marker in raw
    print("Verified retained JPEGs, raw observations and independently decoded fixes.")

def run(record=False):
    coords = expected()
    survey_date = datetime(2024,6,15,12,tzinfo=timezone.utc)
    if survey_date.astimezone().utcoffset() != timedelta(hours=5, minutes=30):
        raise ValueError("Zero-offset runtime comparison requires UTC+05:30 on 2024-06-15. Use --retained for offline evidence verification in any timezone.")
    source = ROOT / "mission-planner-portable.zip"
    assert digest(source.read_bytes()) == ARCHIVE_SHA
    hashes = {}
    with TemporaryDirectory(prefix="photo-georef-") as scratch, ZipFile(source) as z:
        tmp = Path(scratch)
        work = tmp / "survey"
        shutil.copytree(INPUTS,work)
        timestamp = datetime(2024,6,15,12,tzinfo=timezone.utc).timestamp()
        for path in work.glob("*.jpg"):
            os.utime(path,(timestamp,timestamp))
        for name in z.namelist():
            if "/" not in name and name.endswith(".dll"):
                contents = z.read(name)
                (tmp / name).write_bytes(contents)
                if name in ("MissionPlanner.Utilities.dll","MAVLink.dll","MissionPlanner.Comms.dll","MetaDataExtractor.dll","ExifLibrary.dll"):
                    hashes[name] = digest(contents)
        (tmp / "Probe.exe.config").write_bytes(z.read("MissionPlanner.exe.config"))
        csc = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        subprocess.run([str(csc),"/nologo","/r:MissionPlanner.Utilities.dll","/r:"+str(csc.with_name("netstandard.dll")),
                        "/out:Probe.exe",str(HERE/"Probe.cs")], cwd=tmp,check=True)
        process = subprocess.run([str(tmp/"Probe.exe"),str(work)],cwd=tmp,text=True,
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        transcript = process.stdout.replace(str(work),"<synthetic survey>")
        if process.returncode or "MATCHES 1" not in transcript:
            raise RuntimeError(transcript)
        assert "INITIAL_CACHE 0" in transcript
        assert "Photo missing-time NOT PROCESSED. No GPS match" in transcript
        assert "Photo nominal PROCESSED with GPS position found 0 ms away" in transcript
        assert "PHOTO missing-time.jpg 0001-01-01T00:00:00.000 Unspecified" in transcript
        expected_time = "2024-06-15T17:30:00.000"
        result = next(line.split() for line in transcript.splitlines() if line.startswith("RESULT "))
        assert result[1:4] == ["nominal.jpg",expected_time,expected_time] and list(map(float,result[4:])) == coords
        out, = (work/"geotagged").glob("*.jpg")
        assert out.name == "nominal_geotag.jpg"
        tagged = jpeg(out)
        assert tagged["gps"] == coords and tagged["date_taken"] == jpeg(work/"nominal.jpg")["date_taken"]
        for path in INPUTS.iterdir():
            assert path.read_bytes() == (work/path.name).read_bytes()
        report = {"archive_sha256":ARCHIVE_SHA,"release_sha256":hashes,
                  "fixture_sha256":{p.name:digest(p.read_bytes()) for p in sorted(INPUTS.iterdir())},
                  "input":{p.name:jpeg(p) for p in sorted(INPUTS.glob("*.jpg"))},
                  "matched_time":expected_time,"expected_fix":coords,
                  "tagged_file":out.name,"tagged_sha256":digest(out.read_bytes()),"output":tagged}
        if record:
            (HERE/"observation.txt").write_text(transcript,encoding="utf-8")
            (HERE/"result.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
            shutil.copyfile(out,HERE/"nominal_geotag.jpg")
        else:
            assert report == json.loads((HERE/"result.json").read_text())
            assert out.read_bytes() == (HERE/"nominal_geotag.jpg").read_bytes()
    print("Verified real JPEG metadata, one absent timestamp, one matching fix and one tagged output.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--record",action="store_true")
    mode.add_argument("--retained",action="store_true")
    args = parser.parse_args()
    if args.retained:
        check_retained()
    else:
        run(args.record)
