# Mission Planner screen map

Scope: static source from the upstream Mission Planner 1.3.83 tag. A matching release label does not prove that the supplied executable was built from this source. The disconnected main screens were later observed in a modified test copy; see `Mission-Planner-UI-Observations.md` for the precise limits.

`MainV2.cs:851` constructs the Flight Data, Flight Planner and SITL views. `MainV2.cs:3161` registers those views alongside Initial Setup, Software Configuration and Help with `MainSwitcher`. Menu handlers around `MainV2.cs:1295` request the relevant screen. Registration does not mean a screen is visible or usable under every condition.

`GCSViews/InitialSetup.cs` builds the hardware setup page tree. Its `gotAllParams` property compares the received parameter count to the reported count, and individual page registrations test connection status, vehicle type, parameters and display settings. Pages in this source include firmware selection, frame setup, accelerometer and compass calibration, radio setup and failsafe configuration. Plugins may add pages using `AddPluginViewPage`.

`GCSViews/SoftwareConfig.cs` builds the software configuration page tree. Registrations include vehicle-specific tuning views, parameter views, geofence configuration, onboard OSD and MAVFTP. Branches depend on the connected firmware and display configuration; plugins can register additional pages. This is a source-level list of possibilities, not a claim that every page is available for every vehicle.

`mission-planner-binary-evidence/configuration-page-source-inventory.csv` lists 67 explicit `AddBackstageViewPage(typeof(...))` registrations found in those two files, with source line numbers. The small script `research-tools/inventory-setup-pages.py` excludes line-commented calls but does not interpret enclosing conditions, multiline call arguments, plugin registrations or indirect page creation. Use the source for those details. Handler-level mapping, UI navigation, visual rendering and actual calibration or configuration behavior remain outstanding.
