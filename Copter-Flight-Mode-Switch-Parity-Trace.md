# Copter switch positions in Mission Planner and SITL

Mission Planner 1.3.83 and the disarmed Copter simulator agreed on both sides of all five flight-mode switch boundaries. One run swept channel 5 upward and then downward. All 20 samples had a matching RC input report and two subsequent heartbeats reporting the mode configured for the slot highlighted by the release page. The page and simulator ran in separate experiments. [Page capture](mission-planner-gui-faces/flight-mode-display/run3.csv) · [Simulator capture](sitl-evidence/copter-switch-boundaries-run1/switch.csv)

| Integer PWM pair | Page slots, one-based | Copter heartbeat modes |
| --- | --- | --- |
| 1230 / 1231 | 1 / 2 | 0 / 1 |
| 1360 / 1361 | 2 / 3 | 1 / 2 |
| 1490 / 1491 | 3 / 4 | 2 / 3 |
| 1620 / 1621 | 4 / 5 | 3 / 4 |
| 1749 / 1750 | 5 / 6 | 4 / 5 |

The runner read the actual highlighted slots from the original assembly's component capture. In a private, loopback-only network namespace it started a fresh quadcopter simulator, read back `FLTMODE_CH=5` and six distinct mode assignments (0 through 5), then supplied each integer pulse through the simulated RC input. It waited for `RC_CHANNELS.chan5_raw` to equal the sample before counting heartbeats and checked the armed flag on each vehicle heartbeat processed during the sample. The simulator binary SHA-256 was `24afb2e186bcdf66c66d7cb5b88fb7afeaa2a0b89bf63c9d58e4fb2029ac2b54`. The result also records the page capture hash. [Runner](research-tools/sitl-copter-switch-boundaries.py) · [Readbacks and hashes](sitl-evidence/copter-switch-boundaries-run1/result.json) · [Startup log](sitl-evidence/copter-switch-boundaries-run1/sitl.log)

Ten observations cross a slot boundary relative to the preceding sample, five in each direction. The other ten confirm the reported state, including the initial sample and the repeated 1750 at the turnaround. A repeated mode can pass without a new mode change. The CSV stores an input-match flag and the observed mode numbers. Event timing, source component IDs and firmware mode-change reason were outside this capture, so it cannot measure latency or prove which code path produced an individual heartbeat.

In the pinned source, `read_6pos_switch` tests the five thresholds shown above, checks input limits and debounces a changed position for 200 ms of firmware time. Copter then looks up the selected slot and requests its configured mode. These source checks explain why a highlighted setup-page slot alone cannot establish that firmware accepted a change. This run covers steady integer inputs, disarmed, on channel 5. Flight behavior, fractional inputs on a receiver, and transient switch jitter remain untested here. [RC channel implementation](ardupilot-source/ardupilot-master/libraries/RC_Channel/RC_Channel.cpp) · [Copter mode selection](ardupilot-source/ardupilot-master/ArduCopter/RC_Channel_Copter.cpp)

A second launch used a fresh temporary simulator profile and reproduced the first run's 20 rows byte for byte. Across the two runs all 40 steady-state comparisons matched the release component. [Second capture](sitl-evidence/copter-switch-boundaries-run2/switch.csv) and [independent readbacks](sitl-evidence/copter-switch-boundaries-run2/result.json)
