# Original Mission Planner release under Linux/Mono

The portable Mission Planner 1.3.83 ZIP was extracted into a new directory for each interactive run. Its SHA-256 was `ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9`. The app identified its build in the X11 window tree as `1.3.9384.38258`. In the successful disconnected run, all 1,317 original files still matched the ZIP after closing the application. Mission Planner added two log files. See `disconnected/archive-comparison.json`.

## Disconnected session

The subsequent disarmed Copter session has its own [connected capture guide](connected/README.md), including four verified page classes, screenshots, TCP parameter readback and the exact guest fixture.

Ubuntu-E (WSL2) hosted a private Ubuntu 24.04 runtime. Mono 6.8.0.105 started the unmodified release executable on an Xvfb display. The guest had its own network, PID, IPC, mount and user namespaces, a new writable home directory, a software-rendered display, and no attached aircraft or serial devices. The only network interface visible to the app was its private loopback. Executable and companion DLL hashes are in `disconnected/observation.log`. The archived profile contains the normal `DisabledPlugins` preference, listing the bundled optional plugin filenames. No packaged plugin files were removed. The release log records the preference taking effect.

| Operator action | Observed content | Capture |
| --- | --- | --- |
| Start application | Flight Data shows DISARMED, No GPS, zero battery readings and the CONNECT control. Offline maps show missing imagery and hostname errors. | `disconnected/startup.png` |
| Click SETUP | Install Firmware, Install Firmware Legacy, Secure, Optional Hardware and Advanced entries. The central pane is empty. | `disconnected/setup.png` |
| Click CONFIG | The Planner page is selected. UI Language, Telemetry Rates, Log Path, Track Length and other ground station settings are visible. | `disconnected/config.png` |
| Click DATA | Flight Data returns. The HUD, Quick tab, map and CONNECT control are visible. | `disconnected/data-return.png` |

The four `windows-*.txt` files contain the X11 window trees for the corresponding captures. `release.log` records the actual view classes, including ConfigPlanner, and zero parameters received on the two setup screens. The run exercised navigation without changing application or vehicle settings through the UI. Native Windows rendering, plugin behavior, map downloads and aircraft behavior were outside this run.

## Connected Copter session

The original release used its temporary AutoConnect profile to connect over private loopback to a disarmed quadrotor simulator. The application received all 1,431 reported parameters. The DATA screen showed Stabilize and a simulated battery near 12.6 V. The SETUP menu opened Mandatory Hardware. Frame Type displayed Quad and Plus. Flight Modes showed channel 5 at PWM 1800, with slot 6 highlighted in green. Opening FailSafe brought up the propeller reminder, where the observation ended. [Screens and window trees](connected) · [Application log](connected/release.log)

An independent reader on the same simulator's second port recorded disarmed heartbeats, frame class 1, flight-mode channel 5 and assignments 7, 9, 6, 3, 5 and 0. These assignments corresponded to the six labels visible in the GUI. The archive comparison found that all 1,317 packaged files still matched. [Wire capture](connected/serial1-1.bin) · [Decoded observations](connected/serial1-1.json) · [Release file comparison](connected/archive-comparison.json)

A fresh simulator and release extraction were used for the separate slot edit, save, reopen and restore experiment. Another connected run covered sensor pages and captured the battery parameter traffic. The PLAN file round trip used disconnected sessions. [Flight-mode experiment](../gui-original-mono-flight-modes-save-restore-20261122/README.md) · [Sensor page trace](../Copter-Original-Sensor-Pages-Trace.md) · [PLAN file trace](../Original-Mono-Plan-File-Trace.md)

## Reproducing the disconnected run

1. On a WSL2 Ubuntu 24.04 x86-64 installation with unprivileged user namespaces, Bash, apt, dpkg-deb, unzip, Python 3 and ImageMagick, run `bash runtime/prepare.sh`. The script reads the original portable ZIP from the absolute project path on the SSD. It downloads signed Ubuntu package indexes and packages into a private directory under `/tmp`. The host distribution's installed package set is untouched. A previous attempt using the existing package lists hit HTTP 404s for superseded package versions. The included recipe refreshes a private index.
2. Run `bash runtime/observe.sh --profile-no-plugins`. It extracts a new app directory, verifies the release executable hash, starts Bubblewrap with `--unshare-all --cap-drop ALL`, and records the private result directory. Xvfb listens only on its private Unix socket. The guest's only writable host-backed paths are its disposable release extraction and result directory.
3. From the host WSL shell, use `python3 runtime/review.py RUN_ID startup` to inspect the main-window capture. The helper converts the guest XWD to PNG and saves the corresponding window tree and logs. Each subsequent command requires the next step number and a point read from the current capture. For example, the disconnected run used SETUP at (211,118), CONFIG at (260,118), then DATA at (109,117). Finish by writing `done 0 finished` to the next `action-N` file in that guest result directory. Each guest has its own namespace and process IDs.
4. Read the app extraction from `extracted-path.txt`. Run `python3 runtime/compare_archive.py ORIGINAL_ZIP EXTRACTED_DIRECTORY RESULT_JSON` to compare every original file.

## Startup observations

The first Xvfb fixture failed to initialize its keyboard. Supplying a private XKB scratch directory and the guest shell fixed that fixture. With an empty profile, a later run displayed the release splash and a Drone ID plugin notice. Another fresh run stayed on the splash during the observation window. Holding Shift before startup also left plugin-loading messages in the release log on this Mono fixture. The DisabledPlugins profile reached the main window. These outcomes do not identify the cause of the earlier waits. Some Linux-side GDAL wrappers and Windows-only APIs were unavailable, and DNS requests failed in the offline guest.
