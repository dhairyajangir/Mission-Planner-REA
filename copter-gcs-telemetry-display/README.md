# Telemetry loss on the prototype Copter screen

Thirty seconds after the fixture's last position, a heartbeat reset **Last message** to **0 s ago**. The browser still showed the previous position, height and speed. The connection indicator and age describe the message stream as a whole. The screen provides no separate position age.

| Fixture time | Input since preceding observation | Browser observation |
| --- | --- | --- |
| 0 s | Valid position, GPS and battery | 12.5 m, 5.0 m/s, fix type 3, 10 satellites, 12.60 V |
| 30 s | One Copter heartbeat | Same position, height, speed, GPS and voltage. Last message 0 s ago. |
| 31 s | Global position at (0, 0), no GPS fix, unknown satellite count and voltage | Previous position, height and speed remained. GPS read **fix type 1, 255 satellites**. Battery became a dash. |
| 44 s | No further input | Last message 13 s ago. All other observed fields retained their values. |
| 45 s | Valid new position, GPS and battery | 21.0 m, 1.0 m/s, fix type 3, 8 satellites, 12.00 V. The trail gained one point. |

The pinned MAVLink definition assigns the maximum byte value (255) to an unknown satellite count and the maximum unsigned 16-bit value (65535) to missing battery voltage. The prototype displays the satellite sentinel as a literal count and renders the voltage sentinel as a dash. [MAVLink definitions](../mission-planner-1.3.83-source/ExtLibs/Mavlink/message_definitions/common.xml) · [Nominal screen](nominal.png) · [Screen after unknown measurements](unknown_measurements.png)

The fixture sends decoded message objects through the prototype's `StateLink`, advances a test clock, and serves the ordinary HTML and state API on loopback. Headless Chromium reads the six visible fields after each state response. The fixture supplies the connected state directly. No vehicle connection, wire decoder or transport timeout was exercised. A separate release-library test covers Mission Planner 1.3.83's position-source selection when GPS fix quality changes. [Prototype state and HTTP handler](../custom-gcs/customgcs/webui.py) · [Prototype page](../custom-gcs/customgcs/data/ui.html) · [Original Mission Planner GPS study](../Copter-GPS-Fix-Display-Trace.md)

Run `python -B copter-gcs-telemetry-display/replay.py` to check the retained observations and source hashes. Add `--browser PATH_TO_CHROMIUM` from a Python environment with Playwright to replay the five stages. The captures used the installed Chromium 1248 Playwright build on Windows. Earlier command-line DOM dumps timed out or exited before capture. Playwright waited for the actual state response and visible connection label. [Browser readings and API snapshots](observations.json)
