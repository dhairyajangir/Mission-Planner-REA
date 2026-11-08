# Setup-page faces (headless render) trace

Scope: the setup pages of Mission Planner 1.3.83, constructed and drawn by the original `MissionPlanner.exe`, one page at a time, with no vehicle connected. This shows what each page looks like and which controls it creates before any connection. It does **not** show that any page works: nothing was clicked, no parameter list was loaded, and no vehicle or simulator was attached.

## Method

`research-tools/PageFacesProbe.cs` loads `MissionPlanner.exe` from `mission-planner-isolated/` (the executable matches the portable release by SHA-256; `MissionPlanner.Utilities.dll` there is the earlier copy with the user-data and shared-data directories redirected away from the real profile, so this is a modified copy and not an unmodified installation). For each page type it creates the control on its own STA thread (20 s limit), adds it to a form shown far off-screen so that children paint, lays it out at 1000 by 700, lists the controls and their label, button and group texts, and saves a PNG. The first version drew into a form that was never shown and produced blank images; the control inventories from that run were valid, the images were not, and the probe was changed before the cited run.

Pages that reference the network (`ConfigDroneCAN`, `ConfigFirmwareManifest`) and `ConfigFirmware` (not flagged by the scan but expected to download firmware lists) were **not** constructed, so no network access was needed for the pages that were run. Network activity of the probe process was not monitored. The main views (`FlightData`, `FlightPlanner`, `InitialSetup`, `SoftwareConfig`, `Help`, `SITL`) were not constructed.

## Results (`mission-planner-gui-faces/`)

- 57 of the 58 constructed pages rendered: `faces-index.csv` lists control and text counts per page, `faces-texts.md` the visible texts, and `png/` one image each. All are shown in their unconnected, empty state (for example the battery page shows empty fields and a disabled monitor box).
- `ConfigTerminal` constructed when not shown but did not finish within 20 s when shown, and was recorded as a timeout; no image exists for it.
- `ConfigUserDefined` rendered but has only 2 controls and an empty face.
- Nine pages have fewer than five controls (`ConfigAteryxSensors`, `ConfigFirmwareDisabled`, `ConfigHWIDs`, `ConfigMandatory`, `ConfigOptional`, `ConfigParamLoading`, `ConfigREPL`, `ConfigSimplePids`, `ConfigUserDefined`); several of these build their content after a connection or from loaded data, which this run did not do.

## Not established

Behaviour after a vehicle connects, controls created at run time, localisation, theming or scaling, anything that needs parameter data, and original-GUI (unmodified) behaviour. The four pages not rendered are `ConfigDroneCAN`, `ConfigFirmware`, `ConfigFirmwareManifest` and `ConfigTerminal`.

## Main views (second run, `mission-planner-gui-faces/main-views/`)

`Help`, `InitialSetup`, `SoftwareConfig` and `FlightData` were constructed the same way (`FlightPlanner` and `SITL` were skipped because their sources reference the network). `Help` (6 controls), `SoftwareConfig` (4) and `FlightData` (409 controls, HUD included) rendered. `InitialSetup` did not finish within 20 s and was abandoned. With no `MainV2` instance in the harness, `FlightData`'s own update loop threw `NullReferenceException` repeatedly (`console.txt`), so its face shows no live data and says nothing about running behaviour. Same limits as above: unconnected, modified copy, no interaction.

## Connected run (`mission-planner-gui-faces/connected/`)

The same probe was run again after connecting `MainV2.comPort` to a disposable source-built Copter SITL over TCP and downloading its parameters (1,431, see `connect.txt`), and calling each page's `Activate()` before drawing it. 54 of 58 pages rendered; `ConfigFriendlyParams` and `ConfigFriendlyParamsAdv` (about 40 s to build their controls), `ConfigParamLoading` and `ConfigTerminal` did not finish within 20 s. Eight pages created a different number of controls than in the unconnected run (for example `ConfigTradHeli4` 114 to 272, `ConfigFailSafe` 57 to 81, `ConfigUserDefined` 2 to 25), and fields are filled from the simulator's values: the battery page shows monitor type "Analog Voltage and Current", capacity 3300 mAh, voltage divider 10.1 and amps per volt 17. Nothing was clicked or written, only a Copter was used (Plane, Rover and Sub pages would differ), and the data-redirected copy is still not an unmodified installation.

Earlier runs showed a standard .NET "unhandled exception" dialog on the desktop, from `ConfigParamLoading`'s timer throwing `NullReferenceException` when no vehicle is connected. The probe now logs such exceptions (`THREAD-EXCEPTION` lines) instead of showing the dialog.

## Plane, Rover and Sub runs (`mission-planner-gui-faces/connected-arduplane`, `-ardurover`, `-ardusub`)

The connected run was repeated against disposable source-built Plane (1,462 parameters), Rover (1,292) and Sub (1,438) simulators. Each folder has the same files as the Copter run; the per-page status and control counts are in the `faces-index.csv` files, and the claims on each page row summarise them. The same four pages that timed out against Copter (`ConfigFriendlyParams`, `ConfigFriendlyParamsAdv`, `ConfigParamLoading`, `ConfigTerminal`) are the ones that timed out here, with the exact set varying slightly by vehicle (the first two take 40 to 60 s to build). Still no clicks or writes, and still the data-redirected copy.
