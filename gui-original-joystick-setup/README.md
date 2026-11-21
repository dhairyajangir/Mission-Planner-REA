# Original joystick setup page without a controller

Mission Planner 1.3.83 opened **SETUP → Optional Hardware → Joystick** in a disconnected Mono session. The selected menu row and the empty controller selector are visible in the final capture. The page displayed **Enable**, **Save**, **Manual Control**, **Elevons**, axis selectors, reverse checkboxes, output fields and detection buttons. The X window tree contains RC 1 through RC 16. RC 16 is below the screenshot viewport. Only the navigation entries were clicked. [SETUP](setup.png) · [Optional Hardware](optional.png) · [Joystick page](joystick.png) · [Control tree](settled.txt)

The page displayed **Loaded Config for ArduPlane**. The release log identifies the control as `MissionPlanner.Joystick.JoystickSetup` and names the ArduPlane axis and button configuration files. The fresh guest exposed zero Linux input device nodes. During page initialization the application tried to acquire a joystick with a blank name, logged a missing `/dev/input/by-id/` path and then a null reference while querying the button count. The page stayed open. A capture twelve seconds later was byte-identical. [Application trace](release-excerpt.log) · [Guest observation](observation.log) · [Second capture](settled.png)

Ten **Detect** buttons appeared for button assignments despite the empty device selector. In the pinned `ExtLibs/ArduPilot/Joystick/JoystickLinux.cs`, `getNumButtons` starts with a count of ten (line 295) and catches a failed device query. The release logged `getNumButtons 10`. These rows therefore do not establish a physical controller's button count. [Control tree](joystick.txt)

## Ownership and scope

`GCSViews/InitialSetup.cs` lines 278–280 register `Joystick.JoystickSetup` as a child of Optional Hardware when the display option is enabled. The page registration permits a disconnected vehicle. `Joystick/JoystickSetup.cs` declares the control and builds its channel rows (lines 12–19 and 73 onward). The route, module log and rendered page support **mp-page:Joystick.JoystickSetup** and GUI access to **mp-module:Joystick**. Physical input, enablement, saved mappings, outgoing joystick messages and Copter-specific behavior remain unverified by this run. Prior component evidence is recorded in the [joystick workflow trace](../Joystick-Workflow-Trace.md).

The guest used a private Xvfb display, loopback as its sole network interface and a fresh profile with plugins disabled. After exit all 1,317 release files matched the portable ZIP. Two runtime log files were added. [Archive comparison](archive-comparison.json) · [Profile](initial-user-config.xml)

Run `python verify.py` to verify these captures, identities, device count, controls and messages offline. To repeat this observation inside Ubuntu-E, use `python3 -B run.py` with the [prepared guest](../gui-original-mono-evidence-20261122/runtime/prepare.sh) and a separate evidence checkout. A replay writes its own screenshots and logs.
