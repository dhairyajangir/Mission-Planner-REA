# Coverage matrix

`matrix.csv` has one row per Mission Planner 1.3.83 / ArduPilot item (setup pages, source modules, ArduPilot libraries, vehicles, modes) plus one row per workflow in `Reverse-Engineering-Coverage.md`. `summary.md` counts rows per area.

## Columns that carry evidence

| Column | Meaning |
| --- | --- |
| `level` | **L0** inventoried (source exists, nothing else). **L1** a trace or source-map document names it (automatic text match). **L2** the type exists in the REA main-executable index (automatic; Mission Planner rows only). **L3** exercised in SITL (only via `claims.csv`). |
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
