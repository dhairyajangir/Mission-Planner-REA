"""Compare disarmed SITL heartbeats to the release setup-page capture at integer switch boundaries."""
import argparse
import csv
import hashlib
import json
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path

from pymavlink import mavutil

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "mission-planner-gui-faces/flight-mode-display/run3.csv"


def param_read(link, name):
    link.mav.param_request_read_send(1, 1, name.encode("ascii"), -1)
    end = time.monotonic() + 4
    while time.monotonic() < end:
        msg = link.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.2)
        if msg and msg.param_id == name:
            return int(msg.param_value)
    raise RuntimeError(f"No readback for {name}")


def capture(link, rc, pwm, expected_mode):
    packet = struct.pack("<16H", 1500, 1500, 1000, 1500, pwm, *([1500] * 11))
    end = time.monotonic() + 5
    observed_rc = False
    heartbeats = []
    while time.monotonic() < end:
        rc.sendto(packet, ("127.0.0.1", 5501))
        msg = link.recv_match(blocking=True, timeout=0.05)
        if msg is None:
            continue
        if msg.get_type() == "RC_CHANNELS" and msg.chan5_raw == pwm:
            observed_rc = True
        if msg.get_type() == "HEARTBEAT" and msg.get_srcSystem() == 1:
            if msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                raise RuntimeError("Unexpected armed heartbeat")
            if observed_rc:
                heartbeats.append(msg.custom_mode)
                if heartbeats[-2:] == [expected_mode, expected_mode]:
                    break
    return observed_rc, heartbeats


def run(binary, dest):
    if {name for _, name in socket.if_nameindex()} != {"lo"}:
        raise RuntimeError("Run in a private network namespace with only loopback")
    if not binary.is_file():
        raise FileNotFoundError(binary)
    with PAGE.open(newline="", encoding="utf-8") as data:
        points = [(int(r["seed_pwm"]), int(r["actual_slot"])) for r in csv.DictReader(data)
                  if r["case"] == "threshold" and r["seed_pwm"].isdigit()]
    if len(points) != 10:
        raise ValueError("Expected ten integer edge samples from the release page")
    dest.mkdir(parents=True, exist_ok=False)
    parameters = {"FLTMODE_CH": 5, **{f"FLTMODE{i}": i - 1 for i in range(1, 7)}}
    with tempfile.TemporaryDirectory(prefix="copter-switch-") as work, (dest / "sitl.log").open("w") as log:
        defaults = Path(work) / "switch.parm"
        defaults.write_text("".join(f"{n} {v}\n" for n, v in parameters.items()))
        command = [str(binary), "--model", "+", "-w", "-s", "2", "--defaults", str(defaults)]
        proc = subprocess.Popen(command, cwd=work, stdout=log, stderr=subprocess.STDOUT)
        link = None
        try:
            for _ in range(40):
                try:
                    link = mavutil.mavlink_connection("tcp:127.0.0.1:5760", retries=0)
                    break
                except OSError:
                    if proc.poll() is not None:
                        raise RuntimeError(f"Simulator exited with {proc.returncode}")
                    time.sleep(0.25)
            if link is None or link.wait_heartbeat(timeout=15) is None:
                raise RuntimeError("No simulator heartbeat")
            readback = {n: param_read(link, n) for n in parameters}
            if readback != parameters:
                raise ValueError(f"Parameter readback differs: {readback}")
            link.mav.request_data_stream_send(1, 1, mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS, 10, 1)
            link.mav.request_data_stream_send(1, 1, mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 4, 1)
            # Wait for horizontal navigation readiness before testing the GPS-dependent modes.
            gps = link.recv_match(type="GPS_RAW_INT", condition="GPS_RAW_INT.fix_type >= 3",
                                  blocking=True, timeout=35)
            if gps is None:
                raise RuntimeError("No simulated GPS fix")
            time.sleep(6)
            rows = []
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rc, (dest / "switch.csv").open(
                    "w", newline="", encoding="utf-8") as out:
                writer = csv.writer(out)
                writer.writerow(["direction", "pwm", "page_slot", "configured_mode", "received_pwm", "heartbeat_modes"])
                for direction, sequence in [("up", points), ("down", reversed(points))]:
                    for pwm, slot in sequence:
                        mode = readback[f"FLTMODE{slot}"]
                        got_rc, modes = capture(link, rc, pwm, mode)
                        writer.writerow([direction, pwm, slot, mode, got_rc, " ".join(map(str, modes))])
                        out.flush()
                        rows.append(got_rc and modes[-2:] == [mode, mode])
            result = {"binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                      "page_capture_sha256": hashlib.sha256(PAGE.read_bytes()).hexdigest(),
                      "parameters_read_back": readback, "passed": sum(rows), "total": len(rows)}
            (dest / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result))
            if not all(rows):
                raise SystemExit(1)
        finally:
            if link:
                link.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("new_output", type=Path)
    args = parser.parse_args()
    run(args.binary.resolve(), args.new_output.resolve())
