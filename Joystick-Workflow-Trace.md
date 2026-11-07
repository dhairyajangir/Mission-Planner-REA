# Joystick workflow source trace

Scope: how Mission Planner 1.3.83 turns a game controller into `RC_CHANNELS_OVERRIDE` or `MANUAL_CONTROL` messages, plus one library-level probe of the axis-to-PWM mapping. No vehicle, simulator, physical controller or GUI was used. The `MainV2` sender thread, DirectInput, the Linux event-device path and the button actions were read but **not run**.

## Source path

`JoystickBase` lives in `ExtLibs/ArduPilot/Joystick/JoystickBase.cs`; `JoystickWindows.cs` (SharpDX DirectInput) and `JoystickLinux.cs` supply the device. `Joystick/JoystickSetup.cs` is the configuration screen.

- `start` (`JoystickBase.cs:1000`) acquires the device, sets `enabled = true` and starts a background thread running `mainloop` (`:1028`).
- `mainloop` sleeps 50 ms per pass (about 20 Hz), reads the device state, and for each of channels 1 to 18 whose configured axis is not `None` writes the mapped PWM into `MAV.cs.rcoverridechN`. Channels with no axis are never written. If elevons mode is set, channels 1 and 2 are mixed first. It then calls `DoJoystickButtonFunction` (`:364`) only when the link's stream is open.
- The packet is **not** sent from this thread. `MainV2.joysticksend` (`MainV2.cs:2231`) runs every 40 ms, and when `joystick.enabled` it builds a `mavlink_rc_channels_override_t` from the `rcoverridech` values. Channels whose axis is `None` are set to `ushort.MaxValue` (`MainV2.cs:2267` onward). It sends at most once per 50 ms and only when `BytesToWrite < 50`. In SITL-launcher mode (`sitl`) it calls `GCSViews.SITL.rcinput` instead of sending MAVLink.
- With `manual_control` set it sends `MANUAL_CONTROL` (x, y, z, r only) with `target = comPort.MAV.compid` (`MainV2.cs:2395`). ArduPilot compares that field with `sysid_this_mav()` (`libraries/GCS_MAVLink/GCS_Common.cpp:7647`), the system id. They are equal in the default single-vehicle setup (1 and 1). Source reading suggests a vehicle whose `SYSID_THISMAV` differs from component id 1 would ignore these messages; this was not tested.
- `clearRCOverride` (`:292`) sets `enabled = false`, zeros the 18 `rcoverridech` values and sends nine all-zero override messages (six spaced 20 ms apart, then three back to back). Zero means "release override" in `RC_CHANNELS_OVERRIDE`. The UI calls it from the Disable buttons (`Joystick/JoystickSetup.cs:179`, `GCSViews/FlightData.cs:1205`).
- A `SharpDXException` in the loop calls `clearRCOverride` and the lost-joystick action, then ends the thread (`:1133`). Other exceptions are logged and the loop continues.

## Mapping function

`pickchannel` (`:727`) reads `RCn_MIN`, `RCn_MAX` and `RCn_TRIM` from the vehicle's parameter list. If `RCn_MIN` is absent, the list is empty, or reading any of the three throws, it uses 1000 / 2000 / 1500 (the probe covered the `RCn_MIN`-only case). In `manual_control` mode the range is -1000 / 1000 / 0 instead. Channel 3 always uses the midpoint of min and max as its centre, not `RC3_TRIM`. The device value (0 to 65535) is scaled to -500..500 by an `(int)` cast, reversed if configured, passed through `Expo` (`:933`) and clamped to min..max.

## Library-level probe

`research-tools/JoystickMappingProbe.cs` subclasses the original `JoystickBase` with a fake device and calls the compiled `pickchannel`, `Expo`, `mainloop` and `clearRCOverride`. It ran in `mission-planner-isolated/`, whose `MissionPlanner.ArduPilot.dll`, `MAVLink.dll` and `MissionPlanner.Comms.dll` match the portable release by SHA-256; `MissionPlanner.Utilities.dll` is the earlier data-redirected copy, so this is not an unmodified installation. The probe refuses to run if the data directory is under the real profile's AppData folder. The link was never opened, so no packets were sent and button actions were skipped.

Outputs: `coverage/golden/joystick-pickchannel.csv` (1,092 rows: four parameter profiles, channels 1/3/5, 11 device values, reverse on/off, four expo values, plus Pass / UINT16_MAX / None axes) and `coverage/golden/joystick-probe-output.txt`.

Observed in that output (default profile, expo 0):

- Device value 0 gives 1000, 65535 gives 2000, and 32767 and 32768 both give 1500; value 1 gives 1001 and the reverse gives 1999, because of integer truncation toward zero.
- With `RCn_MIN/MAX/TRIM` set to 1100 / 1900 / 1480 channel 1 centres on 1480 but channel 3 centres on 1500.
- With only `RCn_MIN` present the result is the 1000 / 2000 / 1500 default, not a range starting at 1100.
- With positive expo `Expo` leaves the end points unchanged and pulls mid-travel output towards the centre (device value 16384, expo 20: 1300 against 1251 for expo 0).
- The `Pass` axis ("pass-through of trim") produced 1461 for channel 1 with `RC1_TRIM` = 1480, not 1480, because the output scale is not symmetric when trim is off-centre. With the default 1000 / 2000 / 1500 it produced 1500.
- `UINT16_MAX` returns -1, which the sender casts to 65535 ("ignore this channel").
- Lifecycle with the fake device: after the device reported itself invalid, the loop thread ended, `enabled` stayed true, and `rcoverridech1` kept its last value even when the stick moved afterwards. `clearRCOverride` then set `enabled` false and zeroed the values. On Windows `IsJoystickValid` is false only after the DirectInput object is disposed (`JoystickWindows.cs:74`), so this state is reachable only in that case; a physical unplug normally raises `SharpDXException` and takes the clear-and-notify path. That path was not run. Whether `MainV2` would keep sending the stale values in the disposed case follows from `joysticksend` gating on `enabled`, but the sender was not executed.

## Not established

Real device behaviour (DirectInput, hat switches, dead zones in `JoystickAxis`), the `MainV2` send rate and back-pressure on a real link, ArduPilot's response to the override and manual-control messages, button functions, the Linux backend, and any user-interface behaviour. The golden file records what the compiled library returned for the listed inputs only.
