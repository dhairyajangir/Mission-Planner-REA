# Coverage matrix

`matrix.csv` has one row per Mission Planner 1.3.83 / ArduPilot item (setup pages, source modules, ArduPilot libraries, vehicles, modes) plus one row per workflow in `Reverse-Engineering-Coverage.md`. `summary.md` counts rows per area.

## Columns that carry evidence

| Column | Meaning |
| --- | --- |
| `level` | **L0** inventoried (source exists, nothing else). **L1** a trace or source-map document names it (automatic text match). **L2** the type exists in the REA main-executable index (automatic; Mission Planner rows only). **L3** executed against the original library or a simulator (only via `claims.csv`); the cited trace says whether a vehicle or simulator was involved. |
| `fault_injected` | `yes` when drops, corruption, resets or invalid input were injected during the L3 evidence. |
| `gui_kind` | `none`, `modified-copy` (patched data paths / disabled plugins) or `original` (unmodified release executable). A modified copy never counts as original. |
| `target` / `at_target` | Required minimum: `L3`, `L3+fault`, or `L3+gui` (original GUI). Defaults per area are in `build-coverage-matrix.py`. |
| `evidence`, `evidence_sha12` | Files backing an L3 claim and the first 12 hex digits of each file's SHA-256. |

Level is the strongest evidence kind reached, **not breadth**: nearly every L3 row is partial. Read `note` and the cited trace before relying on a row.

## Updating

1. Add or edit a row in `claims.csv` (`row_id`, `level`, `fault_injected`, `gui_kind`, `evidence` as `;`-separated repo-relative paths, `note`).
2. `python research-tools/build-coverage-matrix.py` rewrites `matrix.csv` and `summary.md`.
3. `python research-tools/build-coverage-matrix.py --check` fails if an evidence file is missing, a claim names an unknown row, an L3 claim has no evidence, or the committed matrix is stale. Run it before committing.

Claims are made by hand and only checked for existence, not truth. A cited file proves that a capture exists, not that the claim follows from it.

## Other generated files

`mavlink-surface.csv` (`research-tools/build-mavlink-surface.py`): which Mission Planner types call each `MAVLinkInterface` action method, from IL call sites in `rea-main-index.sqlite`. Direct calls in `MissionPlanner.exe` only; delegates, reflection and other assemblies are not followed, and some compiler-generated closure types appear under their own names rather than their outer type.

`ardupilot-param-names.csv` (`research-tools/build-ardupilot-param-names.py`) lists every parameter name the pinned snapshot's own metadata generator declares, per vehicle. `config-page-params.csv` and `config-page-params-summary.md` (`research-tools/build-config-param-map.py`, `--check` supported) map the quoted parameter names in `GCSViews/ConfigurationView/*.cs` to call shapes and to that list; it is a static text scan and does not see names built at run time.

`page-catalogue.csv` (`research-tools/build-page-catalogue.py`, `--check` supported) lists, for each of 67 screens, the MAVLink calls, `MAV_CMD` names, parameter counts and network/file/dialog/thread references found in its source (static scan). `gaps.md` (`research-tools/build-gap-register.py`, `--check` supported) lists every matrix row that has not reached its target.

`plugin-catalogue.csv` (`research-tools/build-plugin-catalogue.py`, `--check` supported) lists the 39 bundled plugin projects and loose example scripts under `Plugins/` with textual counts of Host calls, MAVLink calls, network, serial/UDP, file, UI, thread and process-start references (static scan only).
