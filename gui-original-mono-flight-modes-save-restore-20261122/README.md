# Copter flight-mode slot save and restore

Mission Planner 1.3.83 changed the first Copter switch slot from Circle to Land after the operator clicked **Save Modes**. A second save restored Circle. Slot 6 remained selected by the simulated radio throughout. Its assigned mode was Stabilize. The primary telemetry log recorded channel 5 at 1800 and 754 disarmed vehicle heartbeats. It contains exactly two parameter-write messages, both for `FLTMODE1`, in the order 9 then 7.

| Checkpoint | Slot 1 shown in GUI | Independent simulator read of all six slots | Disarmed vehicle heartbeats in secondary sample |
| --- | --- | --- | ---: |
| Initial | Circle | 7, 9, 6, 3, 5, 0 | 14 |
| Selected Land, before saving | Land | 7, 9, 6, 3, 5, 0 | 12 |
| Saved, then reopened page | Land | 9, 9, 6, 3, 5, 0 | 12 |
| Restored, then reopened page | Circle | 7, 9, 6, 3, 5, 0 | 12 |

The reopened labels are visible in `reopened-land.png` and `reopened-circle.png`. Navigation visited Frame Type between openings. No frame control was operated. In this Mono session the open combo list rendered as a black rectangle in the screenshot. The closed combo displayed the selected text. During restoration, selecting the first visible item initially kept Land. The operator moved its scrollbar up one position, selected Circle, checked the label, and saved. All other slot values remained unchanged.

## Capture

A fresh copy of the original portable ZIP ran under Mono 6.8.0.105 on Xvfb in Ubuntu-E. A new user profile set the release's optional-plugin preferences and configured AutoConnect for `127.0.0.1:5760`. The exact XML is retained. A fresh, disarmed quad Copter SITL process shared only the private guest environment. Its embedded quad defaults were loaded. The GUI received 1,431 of 1,431 reported parameters. The host network and physical devices were unavailable to the guest. The post-run comparison matched all 1,317 release files against the input ZIP. The executable hash and original dependency hashes are in `observation.log`.

The secondary observer used an independent TCP connection on port 5762. Its only requests were standard `PARAM_REQUEST_READ` packets targeting vehicle 1, component 1. It drained the socket between checkpoints and repeated the nine named requests twice per sample. `serial1-1.bin` through `serial1-4.bin` preserve the raw MAVLink streams. Their JSON files were generated with pymavlink. The compressed TLOG came from Mission Planner's own primary-link telemetry log after the last screenshot. The observed messages establish the behavior of this disarmed simulator session with this release running under Mono.

## Reproduce and verify

The private package-root preparation and XWD-to-PNG review helper are in the sibling `gui-original-mono-evidence-20261122/runtime` directory. Use this experiment's copies of `capture.sh` and `observe.sh` for its connected profile. Run `prepare-observer.sh` first from Ubuntu-E, then `observe.sh --copter`. The disposable guest's actual operator inputs and times are recorded in `observation.log`. The first firmware read happens on connection, followed by explicit capture markers before save, after save and after restoration. `retain-observer.sh` decodes each capture.

Run `python verify.py` with Pillow installed for an offline check. The verifier hashes the files, decodes the relevant v1/v2 MAVLink messages from the raw captures, checks their message-specific CRCs, and compares the independently parsed messages with the recorded pymavlink exports. It checks the primary-link write sequence, active switch PWM, heartbeat arming flags, label pixels after reopening, GUI parameter-download count and the release comparison. `manifest.sha256` lists every file in this directory except itself.
