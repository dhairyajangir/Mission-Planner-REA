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

The first parameter presence check (`copter-param-presence-run1-link-lost-after-absent.txt`, order `CAM_TRIGG_TYPE`, `CAM1_TYPE`, `CAM_TYPE`, `FRAME`, `FRAME_CLASS`, `FRAME_TYPE`, ...) reported `FRAME_CLASS` and `FRAME_TYPE` absent after earlier absent answers; that contradicts the vehicle (`FRAME_CLASS` is 1, read in the second run and in earlier sweeps), so that output is not used. The second, reordered check (`copter-param-presence.txt`) read the present parameters first and gives consistent answers; I did not find the cause of the first run's inconsistency (the machine was busy building unit tests at the time).

## Not covered

The pages that raised exceptions in the state probe (`ConfigGPSOrder`, `ConfigPlanner`, `ConfigSerial`, `ConfigSerialInjectGPS`: a null reference; `ConfigSimplePids`: a missing file `acsim...` under the probe's temp folder) and the one that timed out (`ConfigRawParams`) are not explained here; the probe's detail strings do not carry a stack trace. They probably touch state that the full application creates, but that is a guess.
