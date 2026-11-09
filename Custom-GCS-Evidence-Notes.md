# Evidence notes for a replacement ground station (not a requirements list)

`AGENTS.md` says the owner will decide the custom application's requirements later, and that this archive is not a finished replacement. This file therefore decides nothing. It collects, in one place, behaviours that the evidence in this archive shows a ground station has to cope with, each with the trace that records it and what kind of evidence it is (all are disposable-simulator or source-reading results; nothing was tried on an aircraft, and nothing here was built or tested as an application).

## Vehicle and frame discovery

- A vehicle's frame is described by different parameters depending on firmware and version: `FRAME_CLASS` and `FRAME_TYPE` (Copter, helicopter), `Q_FRAME_CLASS` and `Q_FRAME_TYPE` (QuadPlane), `FRAME_CONFIG` (Sub), `FRAME_CLASS` alone for Blimp, `FRAME_CLASS`/`FRAME_TYPE` with other meanings for Rover (`Copter-Frame-Types-Trace.md`, `Sub-Frame-Types-Trace.md`, `Rover-Frame-Types-Trace.md`, `Blimp-Frame-Types-Trace.md`, `Plane-Frame-Types-Trace.md`). Mission Planner 1.3.83's frame page knows eight classes and six types and shows nothing selected for the others (deca, dodeca-hexa, single, coax, types 12 to 14) (`Copter-Frame-Types-Trace.md` section 2).
- Parameter names change between firmware versions: pages that look for `FRAME` or `CAM_TRIGG_TYPE` are disabled against the snapshot, which has `FRAME_CLASS` and `CAM1_TYPE` (`Setup-Page-Disabled-Reasons-Trace.md`). Asking for parameters one at a time proved unreliable after an unanswered request; downloading the whole list once was reliable.
- A page that assumes a parameter exists without checking can throw (`ConfigGPSOrder` reads `GPS_CAN_NODEID1` that is not there).

## Motor test, the part most affected by vehicle type

- Copter and QuadPlane: `MAV_CMD_DO_MOTOR_TEST` param1 is a **test sequence** (1..N), mapped to a motor by the frame's testing order; the servo output for a motor is not necessarily the motor number (on a QuadPlane motor 1 is output 5). 154 sequences on 23 Copter frames, 27 frames including scripted ones, and 9 of 11 QuadPlane frames matched the source tables (`Copter-Frame-Types-Trace.md`, `Plane-Frame-Types-Trace.md`). The vehicle must be disarmed.
- Sub: the test type must be "board order", param1 is a **zero-based output number**, the vehicle must be armed and the command must be repeated within 500 ms or the vehicle disarms (`Sub-Frame-Types-Trace.md`). With default parameters output 8 is not a motor.
- Rover: param1 selects throttle, steering, throttle left, throttle right (1 to 4); the main sail test (5) is rejected by the vehicle (`Rover-Frame-Types-Trace.md`). Which outputs move depends on the frame's `SERVOn_FUNCTION` values, which a ground station can read from the vehicle.
- Blimp: no motor test command; the stick mixing differs between the fin and motor frames (`Blimp-Frame-Types-Trace.md`).
- Single and coax copters have six test sequences but the Mission Planner page draws eight buttons; buttons beyond the sequences do nothing and raise no message (`Copter-Frame-Types-Trace.md` section 8). The same page labels each button's "Motor Number" from a static file (`APMotorLayout.json`) that lacks some frame types in the firmware (Y4, octa-quad co-rotating types) (section 4), is disabled for Sub, Blimp and fixed-wing Plane, and gives Rover four unlabelled buttons (`Vehicle-Motor-Test-Page-Trace.md`).
- A servo that is a control surface moves on its own while a QuadPlane sits disarmed; a monitor that watches all outputs sees noise (`Plane-Frame-Types-Trace.md`).

## Connections and timing

- A simulator started with a TCP serial port needed a short wait and a priming connection before a client library connected reliably (`Setup-Page-Actions-Trace.md`, items 2 and 3 of the connection notes; the cause was not isolated). A readiness check that looks for a line in a log file can be fooled by an older run's log in the same folder: in the Y4 page probe the wait returned after 1 s because the preparation run's log already held the ready line (`sitl-evidence/motor-layout-page/sitl-extra-y4.log`), and the later connection still worked.
- Wall-clock timeouts interact with simulator speed: a 1 second wait in ArduPilot's own `RotorRunup` test fails when the simulator manages only about ten times real time (`Copter-Frame-Types-Trace.md` section 5).

## What is not here

Anything about flight behaviour on real aircraft, radio links, hardware drivers, or the user interface design the owner may want. Those remain for the owner to decide, and for tests on real equipment that this archive deliberately does not include.
