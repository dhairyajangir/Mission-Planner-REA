"""Regenerate the Copter scope audit from the branch's retained evidence."""
import argparse
import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "coverage/copter-scope.md"
VIEWS = "mission-planner-1.3.83-source/GCSViews"
MENU = "sitl-evidence/live-gui-pages/pages-summary.csv"
HARNESS = "sitl-evidence/page-state/page-state.csv"
REGISTRATIONS = "mission-planner-binary-evidence/configuration-page-source-inventory.csv"

REVIEWS = "coverage/copter-menu-capture-review.csv"
OTHER_FIRMWARE = {"ConfigArduplane", "ConfigArdurover", "ConfigAntennaTracker", "ConfigAteryxSensors", "ConfigAteryx"}
SPECIAL = {
    "ConfigTradHeli4": "Helicopter only",
    "ConfigFrameType": "Legacy Copter frame selector",
    "ConfigHWCompass": "Alternate compass parameter set",
    "ConfigParamLoading": "Parameter download in progress",
    "ConfigFirmware": "Disconnected firmware installer",
    "ConfigFirmwareManifest": "Disconnected firmware installer",
    "ConfigSecureAP": "Disconnected setup",
    "ConfigFirmwareDisabled": "Connected installer placeholder",
}
CORE_MODULES = {
    "MainV2": "Connection and top-level navigation",
    "InitialSetup": "Hardware setup page registration",
    "SoftwareConfig": "Software configuration page registration",
    "FlightData": "HUD and telemetry",
    "FlightPlanner": "Mission read and write",
    "Log": "Offline log browsing",
    "Warnings": "Telemetry warning rules",
}
WORKFLOWS = {
    "connection-telemetry": "Connect and display telemetry",
    "mission-transfer": "Read and write a mission",
    "mission-pause-restart": "Pause and resume a mission",
    "parameters-calibration": "Read and restore parameters",
    "accelerometer-calibration": "Calibrate simulated accelerometers",
    "flight-mode": "Request and observe a mode change",
    "setup-page-action-flightmodes": "Save six switch assignments",
    "fence-workflow": "Read and write a fence",
    "vehicle-internals": "Interpret vehicle state and failsafes",
    "logs": "Retrieve and review flight logs",
    "custom-warnings": "Configure ground-station warnings",
}


def read_csv(name):
    with (ROOT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def unique(rows, key):
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {key} in input")
    return result


def target(row):
    return "met" if row["at_target"] == "yes" else "open"


def review_pages(menu):
    reviews = unique(read_csv(REVIEWS), "page")
    if set(reviews) != set(menu):
        raise ValueError("Saved menu and reviewed captures differ")
    folder = (ROOT / MENU).parent
    for record in reviews.values():
        stem = record["capture"]
        jpeg = (folder / (stem + ".jpg")).read_bytes()
        tree = (folder / (stem + "-controls.txt")).read_bytes()
        if (hashlib.sha256(jpeg).hexdigest() != record["jpeg_sha256"] or
                hashlib.sha256(tree).hexdigest() != record["tree_sha256"]):
            raise ValueError(f"Capture changed since adjudication: {stem}")
        if record["cue_source"] == "reviewed screenshot":
            continue
        if record["cue_source"] != "visible content controls":
            raise ValueError(f"Unknown evidence source: {stem}")
        texts = []
        for entry in re.split(r"(?m)(?=^\d+ \| )", tree.decode("utf-8-sig")):
            match = re.fullmatch(r'\d+ \| [^|\n]+ \| "(.*)" \| client \((-?\d+),(-?\d+)\) '
                                 r'\d+x\d+ \| visible=True \| enabled=(?:True|False)\s*', entry, re.S)
            if match and int(match[2]) >= 172 and int(match[3]) >= 47:
                texts.append(match[1])
        for cue in (record["cue_1"], record["cue_2"]):
            if not any(cue in text for text in texts):
                raise ValueError(f"Missing visible content cue {cue!r} in {stem}")
    return reviews


def generate():
    matrix = unique(read_csv("coverage/matrix.csv"), "row_id")
    pages = {r["item"]: r for r in matrix.values() if r["area"] == "mp-page"}
    states = unique(read_csv(HARNESS), "page")
    menu = unique(read_csv(MENU), "page")
    reviewed = review_pages(menu)
    by_type = unique(reviewed.values(), "page_type")
    registrations = defaultdict(list)
    source = {}
    for entry in read_csv(REGISTRATIONS):
        file, line, name = entry["source_file"], int(entry["line"]), entry["page_type"]
        if file not in source:
            source[file] = (ROOT / VIEWS / file).read_text(encoding="utf-8-sig").splitlines()
        if entry["registration_first_line"] != source[file][line - 1].strip():
            raise ValueError(f"Stale page registration at {file}:{line}")
        registrations[name].append(f"[{file[:-3]} L{line}](../{VIEWS}/{file}#L{line})")
    if set(registrations) != set(pages) or not set(by_type) <= set(pages):
        raise ValueError("Page inventory differs from matrix or menu")
    matched = [pages[k] for k in by_type]
    modes = [r for key, r in matrix.items() if key.startswith("ap-mode:ArduCopter/")]
    mode_files = {p.stem for p in (ROOT / "ardupilot-source/ardupilot-master/ArduCopter").glob("mode_*.cpp")}
    if mode_files != {r["source_ref"].split("/")[-1][:-4] for r in modes}:
        raise ValueError("Copter mode source inventory and matrix differ")
    lines = [
        "# Copter scope and remaining evidence", "",
        f"Saved screenshots and control trees identify the intended page after all {len(menu)} named menu selections in a modified Mission Planner 1.3.83 window. "
        f"The current matrix marks {sum(target(r) == 'met' for r in matched)} of those {len(menu)} page types at their original-GUI target. "
        f"The pinned ArduCopter directory contributes {len(modes)} mode source files. "
        f"{sum(target(r) == 'met' for r in modes)} meet the matrix’s execution target. A mode request refused by the simulator can qualify as execution evidence. Successful entry and behavior require separate observations. "
        "[Coverage definitions](README.md) · [Matrix](matrix.csv)", "",
        "## Work in priority order", "",
        "1. Capture the release application's own connection, Copter HUD, SETUP and CONFIG navigation, then the frame, flight-mode and failsafe pages. Retain package identity, connection state, visible controls and the effect of each action.",
        "2. Resolve differences between component activation and the connected window. Begin with CAN GPS Order, Serial Ports and RTK-GPS Inject. Record which controls the application presents with the same simulator parameters.",
        "3. Exercise Copter workflows end to end. Match a UI action to a simulator acknowledgement, an independent readback and the state shown after reopening the page. Start with flight-mode assignments, parameter restoration and mission transfer.",
        "4. For the remaining source-registered pages, establish which menus and controls are reachable under each relevant firmware, connection, parameter and display-setting combination. Prioritize quadcopter operation before optional peripherals and helicopter-only pages.", "",
        "## Setup and configuration pages", "",
        "Each source link identifies an explicit registration. Each menu link opens its saved screenshot. The review checked visible controls inside the page pane, excluding the navigation bar. All but HW ID had identifying control text. Its screenshot shows a device table with BARO1_DEVID 65540 and BARO2_DEVID 65796. CAN GPS Order showed a title and hint. FailSafe showed its controls after a warning dialog was dismissed. The two battery pages showed different controls. This establishes the page face in each capture; loading data and changing settings require their own evidence. [Per-page review and capture hashes](copter-menu-capture-review.csv) The component column records a separate harness run on Copter SITL. The harness can construct a type which the menu gates out. An enabled root control can still contain disabled children. The final column gives the current matrix level and original-GUI target status for the page across all research.",
        f"[Window capture](../{MENU}) · [Component activation](../{HARNESS}) · [Harness exception follow-up](../sitl-evidence/page-state-exceptions/page-state.csv)", "",
        "| Page | Source registration | Quad scope or captured menu | Component | Level / GUI target |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, row in sorted(pages.items()):
        capture = by_type.get(name)
        scope = SPECIAL.get(name)
        if capture:
            scope = f"[{capture['page']}](../sitl-evidence/live-gui-pages/{capture['capture']}.jpg)"
        if scope is None:
            scope = "Other firmware gate" if name in OTHER_FIRMWARE else "Conditional or shared registration"
        state = states.get(name)
        observed = "No run in this capture" if state is None else state["status"]
        if state and observed == "ok":
            observed = "Enabled" if state["enabled"] == "True" else "Disabled"
        lines.append(f"| {name} | {', '.join(registrations[name])} | {scope} | {observed} | L{row['level']} / {target(row)} |")
    lines += ["", "The two compass registrations depend on the presence of `COMPASS_PRIO1_ID`. The saved Copter parameter list contains it. Frame Type showed a frame-class selector. Antenna Tracker in this menu is the optional tracker UI; the firmware-gated tracker configuration page is a different type. The menu run covered the Mandatory and Optional groups. Advanced, disconnected and software-configuration pages require separate observations. Plugin-added pages are outside the explicit registration inventory. [Copter parameters](../sitl-evidence/setup-page-disabled-reasons/copter-all-parameters.csv)", "",
              "## Modules and workflows", "",
              "These modules own the principal Copter operator tasks. The remaining modules in the repository inventory span shared services, optional features and other workflows. This selection does not establish their vehicle applicability.", "",
              "| Operator task | Owning module | Matrix level | GUI evidence | Target |", "| --- | --- | --- | --- | --- |"]
    for name, purpose in CORE_MODULES.items():
        row = matrix[f"mp-module:{name}"]
        lines.append(f"| {purpose} | [{name}](../{row['source_ref']}) | L{row['level']} | {row['gui_kind'] or 'unclaimed'} | {target(row)} |")
    lines += ["", "The workflow rows below use the ledger’s own targets, typically executed behavior with a fault case. A met workflow target can coexist with an open original-GUI target for the owning module.", "",
              "| Operator workflow | Ledger row | Fault case recorded | GUI evidence | Ledger target |", "| --- | --- | --- | --- | --- |"]
    for key, title in WORKFLOWS.items():
        row = matrix[f"ledger:{key}"]
        evidence = row["evidence"].split(";")[0]
        lines.append(f"| {title} | [{key}](../{evidence}) | {row['fault_injected'] or 'unclaimed'} | {row['gui_kind'] or 'unclaimed'} | {target(row)} |")
    lines += ["", "Frame-specific and firmware evidence also lives in the [Copter frame trace](../Copter-Frame-Types-Trace.md) and [aerial execution trace](../ArduPilot-Aerial-Library-Execution-Trace.md). The mode-file count includes helicopter implementations and custom-mode support. It counts source files once and does not measure branch coverage, flight quality or aircraft behavior.", "",
              "Regenerate from the repository root with `python research-tools/build-copter-scope.py` after rebuilding the coverage matrix. Use `--check` to compare the checked-in report with current inputs.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = generate()
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != result:
            raise SystemExit("Copter scope report is stale")
        print("Copter scope report matches current evidence")
    else:
        OUT.write_text(result, encoding="utf-8", newline="\n")
        print(OUT)
