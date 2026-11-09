# Live GUI attempt, 9 November 2026 (not completed)

Goal: drive the real Mission Planner 1.3.83 window against a disposable Copter simulator with the computer-use tools, so that a GUI observation (connect, frame page, motor test page) is recorded, as opposed to the harness-driven page probes.

What was done:

1. Started a disposable ArduCopter simulator (plus quad) and launched the data-redirected research copy `mission-planner-isolated\MissionPlanner.exe`. The process ran and its window title was "Mission Planner 1.3.83 build 1.3.9384.38258".
2. Asked for control of the window with `request_access` using the names "Mission Planner", "MissionPlanner" and (after creating a temporary Start-menu shortcut named "Mission Planner research copy" that pointed at the research copy) "Mission Planner research copy". Each time the tool answered that the name matches no installed or running application and did not show the user a dialog, even though the process was running. Its list of installed applications is read from the Start menu and was not refreshed by the new shortcut.
3. Removed the temporary shortcut, closed Mission Planner and the simulator. Nothing was clicked or typed in the window.

Result: no GUI observation was made. The tool can only be granted applications it resolves by Start-menu name, so this needs either a Start-menu entry that is present before the session's application list is read, or a person at the keyboard. Everything about the pages in `Copter-Frame-Types-Trace.md` remains harness-driven.


## Follow-up (same day): the window was driven with window messages instead

The computer-use route stayed blocked. I then drove the same research copy of Mission Planner 1.3.83 myself, with Windows window messages posted or sent to that one process's windows only (no desktop mouse, no keystrokes to other applications): `research-tools/gui-driver.ps1` captures the window with `PrintWindow` (PNG files I could read), lists its child windows, posts mouse messages, selects combo box items and sends `BM_CLICK` to buttons. That worked; see `sitl-evidence/live-gui-driven/` and section 10 of `Copter-Frame-Types-Trace.md`. Failed attempts, kept:

- `sitl-evidence/live-gui-uia/uia-tree.txt`: Windows UI Automation shows only plain panes for this WinForms window (no invoke patterns), so it could not press anything.
- `sitl-evidence/live-gui-driven-run1-clicks-missed/`: the first run clicked window coordinates that the program resolved to a container window, not the buttons; nothing moved.
- `sitl-evidence/live-gui-driven-run2-mouse-messages-no-effect/`: the second run clicked the buttons by handle with posted mouse messages; the buttons did not act on them (the same method did work for the plain dialog buttons and the toolbar). The third run used `BM_CLICK` and worked.
