# Effect of time alignment on logged Copter altitude error

Removing the last quarter of simulator truth from a saved Copter log left all 2,745 position estimates in the comparator's whole-log result. It kept using the last available truth altitude for 686 estimates, including one 27.44 seconds later. The reported RMS altitude difference rose from 0.0373 m to 3.5100 m. The position values came from the same recorded flight in all three cases.

| Offline input | Whole-log RMS (m) | Airborne RMS (m) | Estimates classified airborne | Estimates after last truth |
| --- | ---: | ---: | ---: | ---: |
| Original SIM and POS records | 0.0373 | 0.0393 | 2,363 | 0 |
| POS timestamps 1 second later | 0.7157 | 0.7663 | 2,362 | 26 |
| Final quarter of SIM timeline removed | 3.5100 | 3.5879 | 2,627 | 686 |

The original comparator matches each estimate to the most recent SIM timestamp at or before it. It places the estimate in the airborne subset when the matched truth altitude exceeds the initial truth altitude by more than 1 m. In the control each estimate had a simultaneous truth sample. In the truncated copy the last truth altitude was 593.59 m above mean sea level, 9.50 m higher than the original final truth altitude. The held altitude also kept later estimates in the airborne subset. These changes measure the comparator's response to altered evidence from one flight. [Comparator source](../research-tools/analyze-sim-truth-accuracy.py) · [Results](results.json)

## Input and independent check

The control retained the original DataFlash format descriptions and every complete SIM and POS record from the archived plus-frame Copter flight. Its two altitude rows reproduced the sample counts and all four published error statistics for the full log. The archive ends with eight bytes of an unrelated 54-byte IMU record. All SIM and POS frames used here were complete. The clock-shift copy changes only POS timestamps. The gap copy removes SIM records later than 75% of the elapsed truth time. [Archived flight](../sitl-evidence/copter-variants/plus-logged-flight-00000001.BIN.gz) · [Published baseline CSV](../sitl-evidence/copter-variants/plus-sim-truth-accuracy.csv)

For each input, the original Python CLI read a temporary compressed DataFlash file through pymavlink and wrote its usual CSV. An independent reader decoded timestamps and altitudes directly from the record bytes, used a linear time merge and calculated the expected sample count, mean absolute error, RMS, p95 and maximum. Each whole-log and airborne CSV row matched those expectations at the comparator's four-decimal precision. [Replay script](replay.py)

Run `python -B copter-sim-log-alignment-study/replay.py --check` from the research repository in the Linux environment with pymavlink 2.4.50. The script checks the input and comparator hashes and creates temporary files inside the study directory. The retained results contain the sample ages, statistics and source hashes.
