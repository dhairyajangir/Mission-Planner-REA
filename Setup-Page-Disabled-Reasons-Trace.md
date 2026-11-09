# Why eight setup pages are disabled against a Copter simulator

Scope: `Setup-Page-State-Trace.md` recorded that, with the original Mission Planner 1.3.83 pages activated by a harness against a Copter simulator, eight pages end up disabled and five raise exceptions or time out. This trace gives the reason for the disabled ones, from the pages' own `Activate()` source (`GCSViews/ConfigurationView/*.cs`) and from the parameters of the simulator (`research-tools/sitl-param-presence.py`, `sitl-evidence/setup-page-disabled-reasons/`). Disposable simulator, harness, no person.

| Page | What `Activate()` checks | Copter simulator |
|---|---|---|
| ConfigAntennaTracker | firmware is ArduTracker | not (Copter) |
| ConfigArduplane | firmware is ArduPlane | not (Copter) |
| ConfigArdurover | firmware is ArduRover | not (Copter) |
| ConfigAteryx, ConfigAteryxSensors | firmware is Ateryx | not (Copter) |
| ConfigFrameType | parameter `FRAME` exists | `FRAME` absent; the simulator has `FRAME_CLASS` and `FRAME_TYPE` (the page that uses them, `ConfigFrameClassType`, is enabled) |
| ConfigMount | parameter `CAM_TRIGG_TYPE` exists | `CAM_TRIGG_TYPE` absent; this ArduPilot snapshot has `CAM1_TYPE` (and `MNT1_TYPE`, no `MNT_TYPE`), so the page's check is for a parameter name the firmware no longer has |
| ConfigHWESP8266 | reads ESP8266 parameters (`WIFI_SSID1` and others) only if present | `WIFI_SSID1` absent on the simulator; the line of the page that sets `Enabled = false` was not located in its `Activate()`, so this one is the likely reason, not a shown one |

So the disabled state is the page working as written, not a fault in the harness: five pages are meant for other firmware, and two (frame type and mount) are old pages that look for parameters renamed in newer ArduPilot. The mount page being disabled means Mission Planner 1.3.83 cannot configure the camera or gimbal setup of this firmware through that page; I did not check whether another page (for example the full parameter tree) covers it.

## Run history, kept

The first one-name-at-a-time parameter presence check (`copter-param-presence-run1-link-lost-after-absent.txt`, order `CAM_TRIGG_TYPE`, `CAM1_TYPE`, `CAM_TYPE`, `FRAME`, `FRAME_CLASS`, `FRAME_TYPE`, ...) reported `FRAME_CLASS` and `FRAME_TYPE` absent after earlier absent answers; that contradicts the vehicle (`FRAME_CLASS` is 1, read in the second run and in earlier sweeps), so that output is not used. The second, reordered one-name-at-a-time check (`copter-param-presence.txt`) read the present parameters first and gave consistent answers, and the full-list check (`copter-param-presence-full-list.txt`) confirms every answer in it; I did not find the cause of the first run's inconsistency (the machine was busy building unit tests at the time).

## The pages that raised an exception or timed out

`research-tools/run-page-state-exceptions.ps1` reran the six pages against a simulator with the top of the stack trace added to the probe's detail column (`sitl-evidence/page-state-exceptions/`). All four null references are thrown directly inside the page's own `Activate()`. The parameter checks below use the full parameter list of the simulator (1431 of 1431 parameters downloaded, `copter-param-presence-full-list.txt`, `copter-all-parameters.csv`), which replaced the one-name-at-a-time reads that proved unreliable.

| Page | Failure | Cause |
|---|---|---|
| ConfigGPSOrder | NullReferenceException in `Activate()` | **Shown.** `Activate()` checks that `GPS1_CAN_OVRIDE` exists (it does), then reads `GPS_CAN_NODEID1`, `GPS_CAN_NODEID2` and `GPS2_CAN_OVRIDE` without checking; none of the three exists on the simulator, so the lookup returns null. The page assumes a vehicle with a DroneCAN GPS configuration. |
| ConfigPlanner | NullReferenceException in `Activate()` | **Inferred from the source, not shown.** The first thing `Activate()` does is read `MainV2.DisplayConfiguration.displayName`; that object is created by the full application, which the harness does not run. |
| ConfigSerialInjectGPS | NullReferenceException in `Activate()` | **Inferred from the source, not shown.** `Activate()` reads `GCSViews.FlightData.mymap.MapProvider`; the flight data view and its map are not created by the harness. |
| ConfigSerial | NullReferenceException in `Activate()` | **Not explained.** The top frame is `Activate()`; the part that I read (option rules file, baud options, then a MAVFtp download of `@SYS/uarts.txt`) does not show which object is null. The page's serial parameters (`SERIAL1_PROTOCOL`, `SERIAL1_BAUD`, `SERIAL1_OPTIONS`) all exist on the simulator. |
| ConfigSimplePids | FileNotFoundException for `acsimplepids.xml` | **Harness artifact.** `LoadXML(Settings.GetRunningDirectory() + "acsimplepids.xml")`: the file exists next to the executable in the research copy but the probe's redirected running directory (a temp folder) does not contain it. |
| ConfigRawParams | did not finish in 20 s | **Not explained.** The probe abandons the thread; I did not look at what the page was doing. |

So of the six, one failure is a real mismatch between the page and the firmware's parameters (GPS order), two are consistent with the harness not building the whole application, one is a file-path artifact of the harness, and two are unexplained.

## Not covered

The unexplained `ConfigSerial` null and the `ConfigRawParams` timeout; any of these pages in the full application with a person using it.
