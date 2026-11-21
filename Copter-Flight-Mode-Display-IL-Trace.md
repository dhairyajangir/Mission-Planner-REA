# Copter flight-mode display in the release binary

Mission Planner 1.3.83 decides which slot to highlight separately from updating its PWM label. In the retained callback sample that follows removal of both channel parameters, the page highlights slot 1 and still shows `9: 1580`. The two paths in the executable account for this result. [Control capture](mission-planner-gui-faces/flight-mode-display/run3.csv) · [Release IL listing](mission-planner-binary-evidence/copter-flight-mode-display-il.txt)

## Method identity

The decoded `MissionPlanner.exe` has SHA-256 `a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a` and module ID `b0e70e19-ad56-4dc7-bb0b-8e33a4ca21c0`. The REA SQLite index and the independent Cecil decode identify the same two methods on `MissionPlanner.GCSViews.ConfigurationView.ConfigFlightModes`. The index also records the direct call from `timer_Tick` to `readSwitch` at decimal offset 816 (`IL_0330`). [REA index](mission-planner-binary-evidence/rea-main-index.sqlite) · [Metadata-only decoder](research-tools/CopterFlightModeDisplayIl.cs)

| Method | MethodDef token | IL SHA-256 recorded by REA |
| --- | --- | --- |
| `void timer_Tick(object, System.EventArgs)` | `0x06000f3d` | `c5de19f3c2a674b31c0837735a031879412fb55b2309b41b896ce496ad558492` |
| `byte readSwitch(float32)` | `0x06000f3e` | `0fd4200edc4ff4a63f68d2f5fbbf82fee60c4617db54e192ab7b55b04671b792` |

## What the instructions establish

- **Channel and label.** `timer_Tick` initializes PWM to zero at `IL_0033`. When both parameter lookups fail, `IL_006d` branches to `IL_02d1`, past the only two label setters (`IL_0289` and `IL_02cc`). If either parameter exists, `IL_008d` selects `FLTMODE_CH` when present, otherwise `MODE_CH`. The channel value is converted to an integer. Subtracting 5 before the 12-entry switch at `IL_00d4` selects `get_ch5in` through `get_ch16in` in order. Other channel numbers branch at `IL_0109` directly to label formatting with zero PWM. This explains the distinct captured label outcomes for absent parameters and unsupported channel numbers.
- **Thresholds.** `readSwitch` truncates its input with `conv.i4` before comparing. Its zero-based return values for the sampled positive input range are 0 through 1230, 1 for 1231–1360, 2 for 1361–1490, 3 for 1491–1620, 4 for 1621–1749, and 5 starting at 1750. Each synthetic upper boundary plus 0.75 therefore remained in the previous slot, even though its label showed the fraction.
- **Highlight.** `timer_Tick` constructs the control array from `CMB_fmode1` through `CMB_fmode6` beginning at `IL_02d1`. After theming the controls, it uses the returned byte as an array index and passes `CurrentPPMBackground` to the selected control's background-color setter. Interpreting the captured `readSwitch` instructions for the effective PWM of each retained test row reproduced all 34 observed slots. Each of the 12 switch targets also resolved to its respective numbered getter.

The numeric decoder and callback belong to the setup page. The [separate disarmed simulator comparison](Copter-Flight-Mode-Switch-Parity-Trace.md) records which integer inputs were checked against firmware. The earlier [page trace](Copter-Flight-Mode-Display-Trace.md) documents how the controls were sampled.
