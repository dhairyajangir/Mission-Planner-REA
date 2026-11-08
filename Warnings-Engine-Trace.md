# Custom warnings engine trace

Scope: Mission Planner 1.3.83's user-defined warnings (speech, status text and quick-panel colouring), probed at library level with a fake data source object. No vehicle, speech engine, GUI or `warnings.xml` file was used. The dialog (`Warnings/WarningsManager.cs`, `WarningControl.cs`) was read but **not run**.

## Source path

- `ExtLibs/Utilities/Warnings/CustomWarning.cs` holds one rule: a property name on a data source object (`defaultsrc`, the current vehicle state in the app), a comparison (`NONE`, `LT`, `LTEQ`, `EQ`, `GT`, `GTEQ`, `NEQ`), a threshold, a repeat time in seconds, a text template and a type (`SpeakAndText` or `Coloring`). A rule may have one `Child`.
- `GetOptions` (`:57`) lists every property with a non-null value, whatever its type. `GetValue` (`:164`) converts the property value with `Convert.ChangeType(..., double)`. `CheckValue` (`:181`) returns false while `now < lastrepeat + RepeatTime`, otherwise evaluates the comparison and, when true, restarts the repeat window.
- `WarningEngine.MainLoop` (`WarningEngine.cs:85`) runs every 250 ms. For each rule it calls `checkCond` (`:134`): a rule with a child fires only if both `CheckValue` calls return true, parent first. `SpeakAndText` rules speak (when a speech engine exists, waiting in a spin loop while it is busy) and raise `WarningMessage`; `Coloring` rules raise `QuickPanelColoring(name, colour)` when true and `QuickPanelColoring(name, "NoColor")` when not. The loop holds a lock on the shared rule list while it works, and one `try/catch` wraps the whole pass (`:126`).
- The rules are stored in `warnings.xml` in the user data directory, loaded when the class is first used. `MainV2.cs:1020` starts the engine; `:1021` copies messages to the high-priority message field; `:1022` hooks the colouring handler.
- `WarningControl.CB_type_CheckedChanged` (`Warnings/WarningControl.cs:300`) sets the repeat time to 0 when a rule is made a colouring rule, and to 10 for a speech rule.

## Library-level probe

`research-tools/WarningsEngineProbe.cs` uses the compiled `CustomWarning` and `WarningEngine` from `mission-planner-isolated/` (the earlier data-redirected utility DLL; the rule and engine code is unchanged) against a plain object with numeric, bool, enum, string and null properties. Files in `coverage/golden/warnings-*.csv` and `warnings-probe-output.txt`. The time-based files (`warnings-repeat.csv`, `warnings-chain.csv`, `warnings-engine*.csv`) come from real timers, so their timestamps vary by a few tens of milliseconds between runs.

Observed:

- **Comparisons** behave as named, with exact floating-point equality: `0.1 + 0.2` does not equal `0.3`, and a float property of `0.1f` does not equal the threshold `0.1`. With a NaN value only `NEQ` fires.
- **Property types.** Int, float, bool (true counts as 1) and enum properties work. A string property is offered by `GetOptions` but `GetValue` throws `FormatException`.
- **A string property breaks the engine pass.** With a string-typed rule first in the list and a valid numeric rule after it (repeat time 0), no message was produced in 1.2 s; with the valid rule alone, 5 were. The exception is caught outside the loop, so the pass ends at the failing rule every 250 ms and the rules after it are never checked. Rules before it would still run (from the code; not tested).
- **Repeat suppression.** With a 1 s repeat time and a condition that stays true: true at 0 ms, false at 300 and 900 ms, true at 1100 ms, false at 1300, true at 2200.
- **Parent and child.** A parent that is true while its child is false still restarts the parent's repeat window. With a 2 s repeat time, the child became true 300 ms later and the pair did not fire; it fired at 2203 ms.
- **Colouring rules with a non-zero repeat time** flicker. With repeat time 2 s and a condition that stays true, the colour was sent for one 250 ms pass, then `NoColor` for about 1.9 s, then the colour again (events at 8, 2127 and 4229 ms). With repeat time 0 (what the dialog sets) the colour is sent on every pass (0, 255, 518, 783, 1047 ms): the handler is not edge-triggered.
- **Text.** `{name}`, `{value}` and `{warning}` are replaced in every occurrence, numbers use the format `0.##` with the current culture: `12.35` becomes `12,35` under `de-DE`; 0.125 becomes `0.13` and 0.004 becomes `0`; NaN is spoken as `NaN`.

## Not established

How the rules interact with the live vehicle state object, the speech engine, the dialog and `warnings.xml` persistence, and behaviour when the user thread and the engine contend for the rule-list lock (the spin wait on a busy speech engine runs inside that lock; not exercised).
