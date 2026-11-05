# Mission Planner UI observations

Observed 5 November 2026 using the isolated Mission Planner 1.3.83 test copy in `mission-planner-isolated`. This copy has two data-path method bodies redirected to the research workspace and its plugins disabled. A symbolic IL comparison of the utility library is recorded separately; it does not prove equivalence to the unmodified application. The app was disconnected and no physical vehicle was used. These are direct screen observations, not a full UI test or a screenshot archive.

- **Flight Data:** The HUD and quick telemetry panel rendered in the disconnected state. Map tiles included visible request errors and messages that imagery was unavailable. No live telemetry was shown in this UI pass.
- **Flight Planner:** Clicking PLAN opened a map area, empty mission table, mission/fence selection, file controls and Read/Write controls. Map tiles showed the same request-error text. No mission was edited, imported, read or written in the UI.
- **Setup:** Clicking SETUP displayed the disconnected hardware-setup navigation, including Install Firmware, Install Firmware Legacy, Secure, Optional Hardware and Advanced. No firmware operation was started.
- **Configuration:** Clicking CONFIG opened the Planner settings page, with video-device, units, telemetry-rate and other controls. No settings were changed.
- **Simulation:** Clicking SIMULATION displayed a home map and vehicle choices including Plane, Rover, Multirotor and Helicopter. The map displayed request errors. No simulation was launched from this screen.
- **Help:** Clicking HELP displayed documentation links and update controls. No link or update action was invoked.

The attached test-copy launcher logged a normal exit code after the window was closed (`sitl-evidence/isolated-ui-retry/attached-exit.txt`). An earlier detached launch exposed no window and produced no startup log; its PID is retained in the same directory. The screenshots were inspected through computer use and were not saved as separate files. Map errors in this sandboxed test do not establish that a map provider is unavailable in a normal installation.

Remaining UI work includes connection and disconnect through the normal controls, mission editing and transfer, parameter screens, logs, maps with a functioning provider or cache, video, calibration and error recovery. The earlier file-spool application-state test is separate and did not verify the rendered UI.

A later cache-only run of the modified, plugin-disabled application displayed several labeled synthetic zoom-3 tiles from its redirected OpenStreetMap cache. The right portion of the viewport stayed blank. The observed screenshot was not saved; the fixture manifest, script result, and clean application exit are retained under `sitl-evidence/offline-map-ui/`. Real provider imagery and full viewport coverage remain untested.

## Rendered simulator telemetry

A subsequent run used the same modified, plugin-disabled copy with a startup script and `FileSpoolSerial`; a separate local relay connected the spool to the source-built 4.8.0-dev Copter simulator. On Flight Data, the connection control showed DISCONNECT, the vehicle selector showed a quadrotor, and the HUD showed a disarmed vehicle in Stabilize mode. The map footer rendered approximately `-35.3632611, 149.1652300`, matching the simulator's configured home to the displayed precision. Altitude and yaw values were also visible. Map tiles still showed request errors. After the bounded relay ended, the connection control returned to CONNECT, and the test window closed normally.

The app script recorded `open=True`, system 1, component 1 and state coordinates in `sitl-evidence/integrated-ui-telemetry/application-result.txt`; `relay-result.json` records bidirectional bytes without relay errors. The screenshot was inspected through computer use and not saved as a separate file. This establishes one rendered telemetry observation through the scripted spool transport. It does not establish normal TCP/serial connection controls, accurate rendering across changing flight states, functioning map imagery, or an unmodified application run.

## Reading a simulator mission

In a separate disposable 4.8.0-dev Copter run, a startup script in the same modified test copy connected through the file spool and uploaded a two-item home/waypoint mission. Both library upload results were accepted and the simulator returned a count of two (`sitl-evidence/integrated-ui-mission/application-result.txt`). After opening PLAN, the table was initially empty. Clicking **Read** populated one visible waypoint row with latitude `-35.363`, longitude `149.1655`, altitude `20` and relative frame; the home location appeared separately. The application log includes `Getting WP0` and `Getting WP1`; the local relay recorded traffic in both directions without errors. The test window exited normally. The screenshot was inspected and was not saved separately.

The mission was uploaded by script and read through the planner UI. This does not verify manual mission editing, the Write button, a normal serial/TCP connection, other command types or an unmodified application.

## Attempted edit and write

In another disposable run, the same two-item mission was uploaded by script and read through the planner UI. An attempt to replace the waypoint altitude through the grid produced an `Invalid number entered` dialog; the grid then showed `?`. The application had disconnected by the time the error was dismissed, and **Write was not clicked**. The script's recorded simulator readback was still 20 metres (`sitl-evidence/integrated-ui-write/application-result.txt`), but the relative timing of that readback and the attempted edit was not instrumented. The cause of the rejected input is not established; it could involve the automation input sequence. This attempt does not test mission writing or prove that a valid manually entered value would fail.

A second fresh simulator run read the same initial mission, displayed the altitude as 20, and then displayed 25 in the grid. The accessibility `set_value` call timed out, but a subsequent screen observation showed the value had changed. The planner's **Write** control was clicked. The app log records a `MISSION_ITEM_INT` for sequence 1 with altitude `25.0`, followed by a `MISSION_ACK` with type 0; later the app library logged `getWPint` with altitude 25, and the script recorded `readback_alt=25.0` (`sitl-evidence/integrated-ui-write-2/`). The local relay reported no errors and the test app exited normally. The screen showed CONNECT after the click, but the ordered logs establish that the write and later readback occurred before the bounded connection ended.

The planner also sent a home item with an absolute altitude of 584.09 metres; the original scripted upload had supplied a relative-frame home item with altitude zero. The grid's waypoint-radius field changed from 30 to 2 during the interaction, and the app log shows attempted `WP_RADIUS=2` and `WPNAV_RADIUS=200` updates rejected locally because the parameters were absent from its cache. Other radius-setting attempts were also rejected. The precise UI event that changed the radius field was not established. This is one test of a waypoint edit and write through a patched application and custom local transport; it is not a general guarantee that all related settings or other mission types were preserved.

## Parameter list observation

In a separate disposable simulator run, the startup script called the FTP-aware parameter-list method and recorded 1,431 received and 1,431 reported. The connected CONFIG view displayed vehicle-dependent sections, and the Full Parameter List opened with named parameter rows and values. The app displayed a raw-parameter notice stating that this screen does not check minimum or maximum values. A search/edit attempt did not complete before the bounded connection ended; Write Params was not clicked. The script recorded `LOG_DISARMED` as 0 both before and afterward (`sitl-evidence/integrated-ui-params/application-result.txt`). The app exited normally and the relay recorded no errors. This is an observation of a populated screen, not a verification of all displayed values or UI parameter writing.

## Parameter write in local simulator

A later run of the modified, plugin-disabled application displayed `LOG_DISARMED=0` in the Full Parameter List. An edit set it to 1; Write Params displayed a confirmation listing only `LOG_DISARMED: 0 -> 1`, followed by a Saved dialog reporting one successful parameter. The application log recorded the queued edit and a `setParam` response of 1. A separate client read 1 through the simulator's second TCP endpoint; after the test script restored the value, the separate client read 0. The screen still showed 1 after the scripted restore and disconnect, without an intervening refresh. The screenshots were inspected but not saved. See `sitl-evidence/integrated-ui-params-write/` and `Parameter-Workflow-Trace.md` for the transport and limitations.

## Log browser

The isolated test copy opened the previously downloaded simulator DataFlash log in Log Browser. The GPS instance-0 altitude field rendered a graph with values approximately 578–584 metres. The independent parser's 391-sample range was 578.12–584.09 metres. The visible graph, application log and limits are described in `Log-Workflow-Trace.md`; no screenshot file was retained. Playback, export and detailed point-by-point agreement remain untested.
