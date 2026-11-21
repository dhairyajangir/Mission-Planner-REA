import os, subprocess, sys, time
R = "/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload"
sys.path.insert(0, R + "/custom-gcs")
from customgcs import flight, link, params
from pymavlink import mavutil

BIN = os.path.expanduser("~/ap-snapshot/build/sitl/bin/arducopter")
HOME = "-35.363261,149.165230,584.0,0"


def trial(name, hb, setparams):
    subprocess.call(["pkill", "-x", "arducopter"])
    time.sleep(1)
    work = os.path.expanduser("~/probe-arm-" + name)
    subprocess.call(["rm", "-rf", work])
    os.makedirs(work)
    proc = subprocess.Popen([BIN, "-w", "--model", "+", "-I", "0", "-s", "1", "--home", HOME], cwd=work,
                            stdout=open(work + "/sitl.log", "w"), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        end, last = time.time() + 20, 0
        while time.time() < end:
            if hb and time.time() - last > 1:
                conn.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                last = time.time()
            conn.recv_match(blocking=True, timeout=0.2)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 32, 100000, 0, 0, 0, 0, 0)
        base = link.read_params(conn)
        if setparams:
            bad = [r.name for r in params.write(conn, [params.Change("FS_GCS_ENABLE", base.get("FS_GCS_ENABLE"), 1.0),
                                                       params.Change("FS_GCS_TIMEOUT", base.get("FS_GCS_TIMEOUT"), 5.0)]) if not r.ok]
            print(name, "param rejected", bad, flush=True)
        flight.set_mode(conn, "GUIDED", table="copter")
        r = flight.arm(conn, timeout=40.0)
        print(name, "hb=%s params=%s ->" % (hb, setparams), r.ok, r.detail, r.texts if hasattr(r, "texts") else "", flush=True)
    finally:
        subprocess.call(["pkill", "-TERM", "-x", "arducopter"])
        try:
            proc.wait(60)
        except Exception:
            proc.kill()


trial("hb-params", True, True)
trial("nohb-params", False, True)
trial("hb-noparams", True, False)
