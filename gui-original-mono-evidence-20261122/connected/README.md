# Original GUI connected to a disarmed Copter

Mission Planner connected to a fresh simulated quad through its own AutoConnect preference on an isolated loopback interface. The application log records `AutoConnect.NewMavlinkConnection TCP5760` and `TotalReceived 1431 TotalReported 1431`. The [Flight Data screenshot](startup.png) shows DISCONNECT, QUADROTOR, DISARMED, Stabilize and 12.60 V. Its empty map tiles contain offline hostname errors.

| Selected page | Actual view class | Visible content |
| --- | --- | --- |
| [Mandatory Hardware](mandatory.png) | ConfigMandatory | Explanatory text and the expanded setup menu |
| [Frame Type](frame-type.png) | ConfigFrameClassType | Frame Class, Quad, OctaQuad, Y6 and the selected Plus type. The release log names QUAD and PLUS. |
| [Flight Modes](flight-modes.png) | ConfigFlightModes | Current Mode Stabilize, channel 5 PWM 1800, six assignments and the Save Modes button |
| [FailSafe](failsafe.png) | ConfigFailSafe | Propeller warning over the page, with Radio IN, Servo/Motor OUT, battery and GCS controls visible. This session ended with the dialog open. |

On TCP 5762 a separate read-only telemetry client requested the vehicle system ID, frame class, flight-mode channel and six flight-mode assignments. The [decoded packets](serial1-1.json) and [raw stream](serial1-1.bin) record system 1, quad frame class 1, channel 5, and slots 7, 9, 6, 3, 5, 0. The target vehicle's sampled heartbeats were disarmed. The operator clicked only navigation during this session. The [post-run release audit](archive-comparison.json) found all 1,317 files unchanged from the original ZIP.

## Runtime and reproduction

Ubuntu-E hosted the Windows release under Mono 6.8.0.105 and Xvfb. The guest's private network namespace contained loopback only. Its device directory contained only the synthetic device set. [Guest observations](observation.log), [release log](release.log) and [simulator log](copter.log) record the experiment.

Use the [dependency recipe](../runtime/prepare.sh) and [launcher](../runtime/observe.sh). The launcher copies its adjacent `capture.sh` into the guest. For this connected run, place a copy of the launcher in a disposable working folder alongside this directory's exact [capture script](capture.sh), then run `bash observe.sh --copter`. Its [initial user profile](initial-user-config.xml) selects the loopback TCP simulator and disables bundled optional plugins. The launcher supplies the pinned SITL binary read-only and creates a fresh application extraction and home directory. The [navigation helper](../runtime/review.py) records the screen and X11 tree after each operator action. The save-and-restore experiment in the adjacent repository evidence bundle retains source for generating the read-only observer requests. These captures establish this Linux/Mono session only.
