# Live GUI attempt, 9 November 2026 (not completed)

Goal: drive the real Mission Planner 1.3.83 window against a disposable Copter simulator with the computer-use tools, so that a GUI observation (connect, frame page, motor test page) is recorded, as opposed to the harness-driven page probes.

What was done:

1. Started a disposable ArduCopter simulator (plus quad) and launched the data-redirected research copy `mission-planner-isolated\MissionPlanner.exe`. The process ran and its window title was "Mission Planner 1.3.83 build 1.3.9384.38258".
2. Asked for control of the window with `request_access` using the names "Mission Planner", "MissionPlanner" and (after creating a temporary Start-menu shortcut named "Mission Planner research copy" that pointed at the research copy) "Mission Planner research copy". Each time the tool answered that the name matches no installed or running application and did not show the user a dialog, even though the process was running. Its list of installed applications is read from the Start menu and was not refreshed by the new shortcut.
3. Removed the temporary shortcut, closed Mission Planner and the simulator. Nothing was clicked or typed in the window.

Result: no GUI observation was made. The tool can only be granted applications it resolves by Start-menu name, so this needs either a Start-menu entry that is present before the session's application list is read, or a person at the keyboard. Everything about the pages in `Copter-Frame-Types-Trace.md` remains harness-driven.
