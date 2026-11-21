"""Replay telemetry field loss through the prototype state API and browser display."""
import argparse
from collections import deque
from contextlib import contextmanager
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / "custom-gcs"
PAGE = PACKAGE / "customgcs/data/ui.html"
MODULE = PACKAGE / "customgcs/webui.py"
sys.path.insert(0, str(PACKAGE))
from customgcs import webui

IDS = ("s-pos", "s-hs", "s-gps", "s-bat", "s-age", "s-conn")
FIRST = ("-35.100000, 149.200000", "12.5 m / 5.0 m/s", "fix type 3, 10 satellites", "12.60 V")
LOSS = (*FIRST[:2], "fix type 1, 255 satellites", "-")
LAST = ("-35.200000, 149.300000", "21.0 m / 1.0 m/s", "fix type 3, 8 satellites", "12.00 V")
EXPECTED = {"nominal": (*FIRST, "0 s ago"), "heartbeat_only": (*FIRST, "0 s ago"),
            "unknown_measurements": (*LOSS, "0 s ago"), "silence": (*LOSS, "13 s ago"),
            "recovery": (*LAST, "0 s ago")}


def message(kind, **fields):
    return SimpleNamespace(get_type=lambda: kind, get_srcComponent=lambda: 1, **fields)


def position(lat, lon, alt, vx, vy):
    return message("GLOBAL_POSITION_INT", lat=lat, lon=lon, relative_alt=alt, vx=vx, vy=vy, hdg=65535)


def stages():
    return [
        ("nominal", 0, [position(-351000000, 1492000000, 12500, 300, 400),
                        message("GPS_RAW_INT", fix_type=3, satellites_visible=10),
                        message("SYS_STATUS", voltage_battery=12600)]),
        ("heartbeat_only", 30, [message("HEARTBEAT", type=2, base_mode=0, custom_mode=0)]),
        ("unknown_measurements", 31, [position(0, 0, 0, 0, 0),
                                      message("GPS_RAW_INT", fix_type=1, satellites_visible=255),
                                      message("SYS_STATUS", voltage_battery=65535)]),
        ("silence", 44, []),
        ("recovery", 45, [position(-352000000, 1493000000, 21000, 0, 100),
                          message("GPS_RAW_INT", fix_type=3, satellites_visible=8),
                          message("SYS_STATUS", voltage_battery=12000)]),
    ]


@contextmanager
def serve(state):
    handler = webui.make_handler(SimpleNamespace(state=state), "offline-fixture", PAGE.read_text(encoding="utf-8"))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as httpd:
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            yield "http://127.0.0.1:%d/" % httpd.server_port
        finally:
            httpd.shutdown()
            worker.join()


def render(page, url):
    with page.expect_response(lambda response: response.url == url + "api/state" and response.status == 200):
        page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("document.getElementById('s-conn').textContent === 'connected'")
    return {key: page.locator("#" + key).inner_text() for key in IDS}


def hashes():
    return {p.name: hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in (MODULE, PAGE)}


def replay(browser, record_images=False):
    from playwright.sync_api import sync_playwright
    state = webui.State()
    state.connected = True
    state.vehicle = "Copter fixture"
    queue = deque()
    raw = SimpleNamespace(recv_match=lambda **kwargs: queue.popleft() if queue else None)
    stream = webui.StateLink(raw, state, None)
    record = {}
    with sync_playwright() as playwright, serve(state) as url:
        engine = playwright.chromium.launch(executable_path=str(browser), headless=True, chromium_sandbox=True)
        page = engine.new_page()
        for label, second, messages in stages():
            now = SimpleNamespace(time=lambda: 1000 + second)
            with patch.object(webui, "time", now):
                queue.extend(messages)
                while stream.recv_match() is not None:
                    pass
                with urlopen(url + "api/state", timeout=4) as response:
                    snapshot = json.load(response)
                record[label] = {"second": second, "input": [m.get_type() for m in messages],
                                 "state": {k: snapshot[k] for k in ("position", "gps", "battery_v", "speed",
                                                                     "message_age_s", "track")},
                                 "display": render(page, url)}
                if record_images and label in ("nominal", "unknown_measurements"):
                    page.locator("section").filter(has=page.locator("#s-pos")).screenshot(path=HERE / (label + ".png"))
        engine.close()
    return {"source_sha256_lf": hashes(), "stages": record}


def verify(result=None):
    if result is None:
        result = json.loads((HERE / "observations.json").read_text())
    if result["source_sha256_lf"] != hashes():
        raise ValueError("Prototype source differs")
    if set(result["stages"]) != set(EXPECTED):
        raise ValueError("Unexpected stage set")
    for label, second, messages in stages():
        case = result["stages"][label]
        text = [case["display"][key] for key in IDS]
        if text != [*EXPECTED[label], "connected"]:
            raise ValueError((label, text))
        if case["second"] != second or case["input"] != [m.get_type() for m in messages]:
            raise ValueError(label)
        expected_track = [[-35.1, 149.2]] + ([[-35.2, 149.3]] if label == "recovery" else [])
        missing = label in ("unknown_measurements", "silence")
        recovered = label == "recovery"
        expected_state = {"track": expected_track, "position": [*expected_track[-1], 21.0 if recovered else 12.5],
                          "gps": [1, 255] if missing else [3, 8 if recovered else 10],
                          "battery_v": None if missing else 12.0 if recovered else 12.6,
                          "speed": 1.0 if recovered else 5.0, "message_age_s": 13.0 if label == "silence" else 0.0}
        if case["state"] != expected_state:
            raise ValueError((label, case["state"], expected_state))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, help="Chromium executable for the Playwright replay")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    if args.record and not args.browser:
        parser.error("--record requires --browser")
    if args.browser:
        actual = verify(replay(args.browser.resolve(), record_images=args.record))
        if args.record:
            (HERE / "observations.json").write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
        elif actual != verify():
            raise SystemExit("Fresh capture differs from retained observations")
    print("Verified", len(verify()["stages"]), "telemetry display stages.")
