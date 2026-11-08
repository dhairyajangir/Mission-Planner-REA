# Bundled Updater trace

Scope: `mission-planner-1.3.83-source/Updater/Program.cs` (about 190 lines), the small program Mission Planner starts to finish an update, plus a scratch-directory test of the shipped `Updater.exe`. The program contains no network code: downloading the `.new` files is done elsewhere and was not examined. Also covered at inventory level only: `Drivers/`, `Scripts/` and `SikRadio/` (see the end).

## What the code does

After a fixed 5 s pause the updater walks its own directory and every subdirectory. At each directory it deletes `*.old` files, then for each `*.new` file it renames an existing file of that name to `.old` and the `.new` file to the real name, trying up to 10 times with 0.5 s pauses. `Updater.exe.new` is never moved (the code treats it as "can't self update on Windows"). If every move succeeded it deletes `*.old` files in the top directory only and starts `MissionPlanner.exe` (through `mono` on Unix). If any move failed it prints "Update failed, please try it later." and waits for a key. The manifest (`Updater/app.manifest:19`) requires administrator rights.

## Scratch-directory test

`research-tools/test-updater.ps1` ran the shipped `mission-planner-portable/Updater.exe` (SHA-256 in `updater-evidence/updater-exe-sha256.txt`) in a scratch directory with fake files, with the Windows `RunAsInvoker` compatibility flag set on the child so it ran without elevation; nothing outside the scratch directory was touched, and no `MissionPlanner.exe` existed there to start. Output is in `updater-evidence/`. Because stdout was redirected, the final key wait threw an unhandled `InvalidOperationException` in the failure cases; that is a test-harness artefact.

- **Clean directory** (4 `.new` files including one in a subdirectory and the self-update file): finished in 5.3 s. Existing files were replaced, `stale.dll.old` was deleted, the top-level `a.dll.old` was removed after success, `sub\d.dll.old` was left behind (the final cleanup is not recursive), and `Updater.exe.new` stayed in place.
- **One file locked** (`a.dll` held open exclusively): after the retries it reported failure at about 18 s. `a.dll` stayed old and its `.new` stayed in place, `b.dll` in the same directory was still updated, and the subdirectory was **not processed** (`sub\d.dll` stayed old, its `.new` untouched). The result is a mixed set of old and new files. The cause is `all_done = all_done && UpdateFiles(subdir)`, which skips the recursive call once any earlier move failed.
- **A file literally named `.new`**: the guard that should skip it compares the whole path with `".new"` and never matches, so the updater tried to move it (by the code, onto its own directory path, which is inferred; the exception text was not examined), retried, reported failure and, as above, skipped the subdirectory while `a.dll` was updated.

The test used fake file contents and no real update package. Whether Mission Planner's real update flow can produce these states (locked DLLs are the normal reason it needs the updater) was not tested.

## Inventory only (not run)

- `Drivers/`: 25 `.inf` and 25 `.cat` driver packages (Arduino, ChibiOS and others), four DLLs, three executables, two `.sys` files and two batch files. Nothing was installed or run.
- `Scripts/`: 19 Python scripts for Mission Planner's built-in Python console (examples, `cubeorange.py`, `debugenv.py`, `datetime.py`). They use objects (`cs`, `MAV`, `Script`) that exist only inside the application, so they were not run.
- `SikRadio/`: 23 C# files of the SiK radio configuration tool (serial AT-command interface to radio hardware), plus firmware `.bin` files. Not read in detail and not run; it needs radio hardware or a simulated serial device.
