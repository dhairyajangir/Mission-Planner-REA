# SiK radio configuration code against a simulated radio

Scope: the command and connect routines of Mission Planner 1.3.83's radio configuration page (`Radio/Sikradio.cs`: `doCommand` at `:1938`, `doConnect` at `:2007`), run from the original `MissionPlanner.exe` against a **simulated radio written for this test** (`research-tools/SikRadioSimProbe.cs`). No radio hardware, real serial port, firmware upload or real SiK firmware was involved. The simulation only models what the code itself expects (an echoed command line followed by a reply, and "OK" after `+++`), so the results show how the code reacts to those replies, not how a radio behaves. Firmware upload (`Uploader.cs`), XModem, the settings page and the RFD900 helper classes in `SikRadio/` were not exercised. Output: `radio-sim-evidence/`.

## Source behaviour

`doCommand` sends a bare CR/LF, reads one line, waits 50 ms, writes the command, and reads the echo. If the echo does not contain the command it clears the input and retries once; otherwise it returns the next line (or, for multi-line replies, everything that arrives within a fixed 1 s window). `doConnect` writes `ATO`, then `+`, `+`, `+` with 200 ms gaps and fixed waits of 1.5 s, repeating up to four times if nothing arrives, sends `AT&T` and `ATI`, and returns true only if the `ATI` reply matches the regular expression `SiK\s+(.*)\s+on\s+(.*)`.

## Results (simulated radio)

| Case | What the code did |
| --- | --- |
| `ATI`, `ATI7`, multi-line `ATI5` | Returned the reply line(s); the multi-line call always waited about 1 s |
| unknown command `ATX` | Returned the radio's `ERROR` line unchanged (no error handling in `doCommand`) |
| radio does not echo | Sent the command twice, returned an empty string after 0.1 s |
| radio silent | Returned an empty string after 4.1 s |
| garbage reply | Returned the control characters it received |
| `doConnect`, normal radio | True after 3.6 s; the radio saw `ATO`, `+++`, `AT&T`, `ATI` |
| `doConnect`, `ATI` replies `RFD900x V3.1 on RFD900X` (no "SiK") | **False** after 3.5 s even though the link was fine |
| `doConnect`, no "OK" after `+++` | Sent `+++` four times, then false after 13.7 s |
| `doConnect`, silent radio | False after 13.7 s |

The RFD900 case matters only for this routine: the same page elsewhere parses `RFD ... on ...` version strings (`SikRadio/RFD900.cs:1953`), so other code paths may handle such radios; that was not tested. Real firmware replies were not available, so the reply texts are my assumptions from the code.

## Not established

Behaviour with real SiK or RFD900 firmware, real timing and noise on a serial link, settings read and write (`ATI5` parsing into the page), encryption keys, remote-radio (`RT`) commands, firmware upload, and the `SikRadio/` folder's RFD900 classes (2,774 lines in `RFD900.cs`).
