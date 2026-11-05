# Plugin lifecycle source trace

Scope: selected paths in Mission Planner 1.3.83 source. The main UI tests used a copy with its plugin directory disabled, so they do not verify plugin behavior. An earlier startup attempt with plugins enabled reached plugin loading and showed a modal; individual plugins were not exercised.

`Plugin/PluginLoader.cs:101` handles DLL candidates. It filters certain filenames, checks the configured disabled-plugin list, skips files whose name also exists in the application directory, installs an assembly-resolution handler and loads eligible files with `Assembly.LoadFile`. `InitPlugin` at `:148` looks for types assignable to the plugin base class, constructs them, assigns a `PluginHost` and filename, and calls `Init`. A successful `Init` places an instance in a loading list; errors are caught and logged.

The plugin-directory scan at `:209` also finds `.cs` files. It processes `//loadassembly:` directives, tries Roslyn compilation and has a fallback compiler path. DLL candidates are loaded separately, and `PluginInit` invokes each pending plugin's `Loaded` method before adding successful instances to the active list. These operations depend on the source version and current configuration; the trace does not enumerate every dynamic dependency or generated assembly.

`MainV2.cs:2503` iterates loaded plugins and calls `Loop` when their configured `loopratehz` and next-run time permit. The shutdown path around `:2540` calls `Exit` and removes instances. `Plugin/PluginUI.cs` maintains disabled plugin names and marks a restart as required when that configuration changes.

REA's index of the portable executable identifies `PluginLoader.Load` as method token `0x060007ad`, `InitPlugin` as `0x060007ae`, `LoadAll` as `0x060007af`, and `PluginInit` as `0x060007b0` (`mission-planner-binary-evidence/rea-main-index.sqlite`). These are binary member identities and recorded IL hashes, not proof that source and binary behavior agree in every branch.

These entry points make plugin loading part of the application's behavior, but bundled plugins' side effects, UI additions, timing and security isolation have not been tested here. Source-level registration is not proof that every plugin loads successfully in a particular build.

## Isolated loader test

A standalone harness invoked `PluginLoader.Load` from the distributed 1.3.83 `MissionPlanner.exe` with synthetic fixture DLLs. The executable in the test directory matched the portable executable by SHA-256; the same directory contains the previously modified utility DLL, so this is not an unmodified installation test. The harness used a fresh disabled-name list: loading a disabled copy produced no fixture events. Loading the enabled fixture called `Init` on four concrete classes. One returned false, one threw a synthetic exception, and two returned true. The harness then invoked the private `PluginInit` method via reflection: the class whose `Loaded` returned false stayed inactive, while the class whose `Loaded` returned true became the only active fixture. The loader logged the synthetic exception and also logged a failed attempt to instantiate the fixture's abstract base class. The harness directly called the accepted fixture's `Exit` method afterward.

Events, loader logs and fixture files are in `sitl-evidence/plugin-loader-probe/`; source is `research-tools/SyntheticPluginFixture.cs` and `research-tools/PluginLoaderProbe.cs`. This verifies selected loader decisions for synthetic DLLs only. The harness did not use the application directory scanner, source-code compilation path, scheduler, application shutdown, UI integration, bundled plugins or a physical vehicle. The direct `Exit` call does not establish that the real application invokes it during shutdown.
