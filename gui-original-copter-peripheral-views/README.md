# Connected Copter peripheral views

Mission Planner 1.3.83 ran under Mono in Ubuntu-E with a separate X server, temporary user profile and private network namespace for each attempt. Its AutoConnect profile selects the simulated ArduCopter on TCP 127.0.0.1:5760. The release archive and simulator hashes are checked by the [launcher](../research-tools/observe-original-copter-sensors.sh). The profile disables bundled plugins for this test. The release also tries to retrieve online data during startup. The private guest logs DNS resolution failures for those requests.

## What the unmodified application showed

Under `mono --interp`, run `sensors-3hWrUmfA` connected to the pinned ArduCopter 4.8.0-dev quad. The operator selected SETUP, expanded Mandatory Hardware, opened Serial Ports, expanded Optional Hardware, opened RTK/GPS Inject, scrolled the menu, opened CAN GPS Order and returned to DATA. The final HUD displayed DISARMED and Stabilize. The recorder then ended the disposable session. [Navigation log](observation.log) · [Application log](release.log) · [Final HUD](final-hud.png)

| Page | Observed content in the original Linux/Mono window |
| --- | --- |
| [Serial Ports](serial.png) | Rows 1–7 each displayed a Set Bitmask button. Row 1 showed 57600 and MAVLink2. The note at the bottom said changes take effect after a board reboot. |
| [RTK/GPS Inject](rtk.png) | The pane showed 115200, a Connect button, zero input and output rates, an empty Messages Seen line and red RTCM indicators. Send NTRIP GGA was checked. NTRIP v1.0 and automatic receiver configuration were unchecked. |
| [CAN GPS Order](can-gps-order.png) | The pane showed the UAVCAN GPS Order title and an empty table with Order, NodeID, Name, GPS1 and GPS2 headers. The simulator had no attached CAN GPS receiver. |

Three earlier fresh extractions stopped at the splash using the default Mono runtime. Each simulator logged that it was waiting for a connection. A single thread dump taken during `sensors-Yqrjmvst` placed the UI thread in Newtonsoft.Json `CreateList`, reached through `FromJSON`, `AutoConnect.Start` and `MainV2.OnLoad`. The underlying cause remains undetermined. The fourth launch used the same application and profile with the [interpreter retry](observe-interpreted.py). [Startup attempts](startup-attempts) · [Verification](verification.json)

## Earlier evidence

| Page | Modified Windows window | Standalone component with Copter SITL |
| --- | --- | --- |
| Serial Ports | The pane showed SERIAL PORT 1 and Set Bitmask. | ConfigSerial.Activate raised NullReferenceException. |
| CAN GPS Order | The pane showed UAVCAN GPS Order and Set the GPS order if required. | ConfigGPSOrder.Activate raised NullReferenceException. |
| RTK-GPS Inject | The pane showed NTRIP protocol v1.0 and NTRIP GGA options. | ConfigSerialInjectGPS.Activate raised NullReferenceException. |

[Modified-window page adjudication](../coverage/copter-menu-capture-review.csv) · [Component exception records](../sitl-evidence/page-state-exceptions/page-state.csv)

## Vehicle traffic

The telemetry log contains 339 ArduCopter heartbeat samples. Every sample reports disarmed, including the samples bracketing the three captures. The archive comparison matched all 1,317 original files. [Telemetry replay](verification.json) · [Archive comparison](archive-comparison.json)

| Six seconds beginning at the recorded page-selection second | Ground-station traffic in the telemetry log |
| --- | --- |
| Serial Ports | Six heartbeats and 12 MAVFTP requests. Mission Planner reset the FTP sessions, opened `@SYS/uarts.txt` read-only and made ten file-read requests. Its log records end of file. |
| RTK/GPS Inject | Six heartbeats, one time synchronization message, six data-stream requests, one SET_MESSAGE_INTERVAL command and three REQUEST_MESSAGE commands. These requests coincided with the view. |
| CAN GPS Order | Six heartbeats. |

Across the full retained log, the ground station sent zero PARAM_SET, PARAM_EXT_SET, GPS_INJECT_DATA, GPS_RTCM_DATA or SERIAL_CONTROL messages. The record covers the unmodified Linux/Mono page displays in this disarmed simulator. Physical receiver operation, corrections delivery, port configuration changes and native Windows behavior remain untested here. [Telemetry file](vehicle.tlog.gz) · [Serial page activation source](../mission-planner-1.3.83-source/GCSViews/ConfigurationView/ConfigSerial.cs#L77)

## Reproduction

From the repository root in Ubuntu-E with the prepared guest, run `python3 gui-original-copter-peripheral-views/observe-interpreted.py` to reproduce the successful launch. Its capture script starts `mono --interp MissionPlanner.exe`. The three earlier attempts used `bash research-tools/observe-original-copter-sensors.sh --copter`. Both launchers print a fresh run ID. [Retained successful guest script](capture.sh)

Work in a separate copy when collecting new evidence because the recorder writes to its own directory. Use `python3 gui-original-copter-peripheral-views/observe.py RUN_ID startup 0` to inspect the first screenshot. Each subsequent invocation takes a label, a monotonically increasing action number and the two pixel coordinates of a visible navigation control. The guest records the click, waits four seconds and captures the X window tree and screen. A normal finish uses `finish NEXT_ACTION`. A splash-only observation uses `startup-stop NEXT_ACTION`. The recorder copies the session logs, telemetry when present, and the archive comparison to the evidence directory. Run `python gui-original-copter-peripheral-views/verify.py --check` from the repository root to replay the retained results.
