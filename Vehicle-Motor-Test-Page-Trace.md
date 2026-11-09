# Motor test page against Sub, Rover, Plane and Blimp simulators

Scope: what the original Mission Planner 1.3.83 `ConfigMotorTest` page draws when it is built (by a harness, not a person, nothing pressed) against disposable simulators of vehicles other than Copter. Method as in `Copter-Frame-Types-Trace.md` section 6: `research-tools/PageMotorLayoutProbe.cs`, run by `research-tools/run-motor-layout-vehicles.ps1`; evidence in `sitl-evidence/motor-layout-page-vehicles/`. In every row the probe's own status was "ok". The runner ended with a PowerShell error from its cleanup (`$p.Kill()` on a value that was not a process object); all eleven result files had been written by then and the leftover Blimp simulator was killed by hand.

| Simulator | Page enabled | Buttons drawn | "Motor Number" labels | Class / type text |
|---|---|---|---|---|
| ArduSub, vectored | **no** | 8 | none | unknown / unknown |
| ArduBlimp | **no** | 8 | none | unknown / unknown |
| ArduPlane, plane (fixed wing) | **no** | 8 | none | unknown / unknown |
| QuadPlane, quadplane | yes | 4 | 4 | Quad / X |
| QuadPlane, quadplane-tri | yes | 4 | 4 | Tri / X |
| ArduPlane, firefly | yes | 6 | 6 | Y6 / Y6F |
| ArduPlane, plane-tailsitter | yes | 4 | none | Single/Dual / X |
| ArduRover, rover | yes | 4 | none | unknown / unknown |
| ArduRover, rover-skid | yes | 4 | none | unknown / unknown |
| ArduRover, rover-omni3mecanum | yes | 4 | none | unknown / unknown |
| ArduRover, sailboat | yes | 4 | none | unknown / unknown |

Reading it against the sweeps in the other traces:

- **ArduSub and ArduBlimp**: the page disables itself (the vehicle has none of the parameters it looks for, `FRAME`, `FRAME_TYPE` or `Q_FRAME_TYPE`; Sub has `FRAME_CONFIG`). The page therefore cannot be used to test Sub thrusters, which the vehicle's motor test supports (`Sub-Frame-Types-Trace.md`). The disabled page still draws eight buttons.
- **QuadPlane**: the buttons and labels follow `FRAME_CLASS` and `FRAME_TYPE` through the `Q_` parameters. The label's "Motor Number" is the motor number, not the servo output; on these frames motor 1 is output 5 (`Plane-Frame-Types-Trace.md`).
- **Fixed-wing plane**: disabled, eight buttons drawn.
- **Single-motor tailsitter**: four buttons, no labels, matching the four sequences the tailsitter motor test addresses (none of which exist on this frame's outputs, so pressing them would do nothing; not pressed).
- **Rover**: four buttons "Test motor A to D" with no labels, class and type shown as unknown. The vehicle's own tests are 1 throttle, 2 steering, 3 throttle left, 4 throttle right (`Rover-Frame-Types-Trace.md`), so the buttons map to those four; nothing on the page says which button is which, and the main sail test (5) is not offered, consistent with it being unreachable.

Not covered: pressing the buttons on these vehicles; the page's other tabs for these vehicles; a person using it.
