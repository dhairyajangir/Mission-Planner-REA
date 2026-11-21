# Copter flight-mode switch display in Mission Planner 1.3.83

The setup page highlights slot 1 when the Copter state has no flight-mode channel parameter. Its PWM label depends on what the page displayed previously. On a fresh page it stayed at the designer value `0`. After a valid channel 9 sample, clearing both channel parameters left the label at `9: 1580` while the highlight moved from slot 4 to slot 1.

The earlier [setup page actions trace](Setup-Page-Actions-Trace.md) covers reading and saving mode assignments against SITL. This probe exercises the original page's `timer_Tick` callback with a disconnected MAVLink interface. It reads the label and all six combo-box background colors after each callback. It does not start Mission Planner's main window, activate the page, send parameter writes, or emulate a receiver. Treat the observations as original-assembly component execution. The original-GUI coverage target remains open.

## Channel selection and thresholds

The probe supplied one distinct PWM value on each channel from 5 through 16 in turn, with every other channel set to 1000. The label identified the seeded channel and value in all 12 cases. A lone `MODE_CH=7` worked. With both parameters set, `FLTMODE_CH=9` took precedence over `MODE_CH=7`. Setting `FLTMODE_CH` to 0, 4, or 17 still took precedence over a valid `MODE_CH=7`. All three showed the unsupported channel number, zero PWM, and slot 1.

| Switches to slot | Boundary sample in previous slot | Fractional sample still in previous slot | First integer in new slot |
| --- | ---: | ---: | ---: |
| 2 | 1230 | 1230.75 | 1231 |
| 3 | 1360 | 1360.75 | 1361 |
| 4 | 1490 | 1490.75 | 1491 |
| 5 | 1620 | 1620.75 | 1621 |
| 6 | 1749 | 1749.75 | 1750 |

The fractional values are synthetic. The label retained each fraction, while the highlighted slot agreed with the integer conversion in [ConfigFlightModes.cs](mission-planner-1.3.83-source/GCSViews/ConfigurationView/ConfigFlightModes.cs). The probe observed exactly one selected color after every callback, including transitions back to lower slots.

## Reproduction and captures

On Windows with Python 3 and .NET Framework 4.x, run from the research repository:

```powershell
python research-tools/run-copter-flight-mode-display.py "$env:TEMP\flight-mode-display.csv"
```

The [runner](research-tools/run-copter-flight-mode-display.py) takes the executable and dependency DLLs from the root of the stored portable release ZIP into a fresh temporary directory. The [probe](research-tools/CopterFlightModeDisplayProbe.cs) sets the release's user-data override to a temporary profile, assigns the Copter firmware enum, and sets the highlight color to lime so it can test which combo box the callback selects. The controls are instantiated without displaying a window. The ZIP SHA-256 was `ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9`. The executable SHA-256 was `a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a`.

Two development attempts stopped before producing a CSV. The first assumed a default firmware value. The second dereferenced a null transport while checking for a connection. Both emitted an unhandled exception and the runner timed out. The corrected harness explicitly selects Copter, accepts a missing transport as disconnected, and reports exceptions before exiting. Two fresh processes then produced 34 matching rows apiece. The [first passing capture](mission-planner-gui-faces/flight-mode-display/run3.csv) and [repeat](mission-planner-gui-faces/flight-mode-display/repeat.csv) share SHA-256 `116d912364315c6a8acd1dd9bbc565df420c8109495c023b08dde0bf278ad9a5`.
