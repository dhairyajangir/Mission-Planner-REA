# Phase 0 baseline (7 November 2026)

Environment and reproducibility state for continuing the research. Branch `phase2` (not pushed).

## Workspace

- Working tree: `C:\Users\think\OneDrive\Documents\ChatGPT\The Drone Project\mission-planner-rea-upload`. It is byte-identical to GitHub `main` at `ba5483c` apart from 6 symbolic-link entries Windows cannot create (marked `assume-unchanged`: `supportproxy-deps/.../libtdb*`, two `changelog.Debian.gz`, two `supportproxy_w0current`).
- Git history is shared with the sibling bare repository `../research-upload.git` through `.git/objects/info/alternates`, because C: had about 6.6 GB free and a second 2 GB copy did not fit. **Do not delete or move `research-upload.git`** without running `git repack -a -d` here first.
- The four Git LFS files (`.msi`, `.cab`, `.zip`, `rea-remaining-index.sqlite`) are real files locally. Their SHA-256 values match the committed LFS pointers; they are marked `assume-unchanged` so Git does not copy them into `.git/lfs`.
- The parent folder `The Drone Project` also has an empty-history repository covering other project files; this repository is nested inside it.

## Tool versions

| Tool | State |
| --- | --- |
| REA (`research-tools/node_modules/rea-agents`) | 6.8.0. **Needs Node 22.15 or newer** (`node:zlib.zstdDecompress`). Host Node 22.13.0 fails at start-up. Node 24.22.1 exists at `C:\Users\think\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`; set `MPREA_NODE` to it. That path belongs to another application's cache and may disappear. |
| Python 3.10.11 (Windows) | Present; no `pymavlink`. |
| WSL2 Ubuntu 24.04 | Present. `~/venv-ap` has `pymavlink`. gcc present; **gdb not installed** (needed for the NaN-crash investigation). |
| SITL | `~/ardupilot/build/sitl/bin/arducopter` (built 28 Oct) and source-built binaries kept under `sitl-evidence/`. |
| .NET Framework `csc.exe` | `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`. No .NET SDK. |

## Path portability

Machine-specific paths were removed from 19 scripts in `research-tools/`; they import `env_paths.py` (see `env.example` for the overrides `MPREA_NODE`, `MPREA_ARDUPILOT_ZIP`, `MPREA_SUPPORTPROXY_BIND_SHIM`, `MPREA_INTEGRATION_DIR`). No `.cs` probe contained a hard-coded user path. Existing probes may still assume relative layouts from the original session; each is untested on this host unless noted in a trace.

## Gap found: evidence stored outside the repository

`verify-research-evidence.py` and the index builders use `integration-research/`, which lives next to this repository and is **not in Git**: `ardupilot-source-index.sqlite` (114 MB), `ardupilot-submodules-index.sqlite` (320 MB), `mission-planner-source-index.sqlite` (70 MB), `mission-planner-normalized-source-index.sqlite` (108 MB) and their summary JSON files. The ledger's source-search claims depend on them. They are not copied into the repository (disk space, hash-checked artifacts); `env_paths.INTEGRATION_DIR` finds them in `./integration-research` or the parent folder.

## Verifier baseline

`python research-tools/verify-research-evidence.py` (about 60 s) with the index directory found: **241 of 241 checks pass**, and the rewritten `research-evidence-verification.json` is byte-identical to the committed file. This shows the stored captures are internally consistent. It does not show that any claim is true.

## Added in this phase

- `coverage/` matrix (360 rows) and `research-tools/build-coverage-matrix.py`; see `coverage/README.md`.
- `coverage/mavlink-surface.csv`: IL call sites from `MissionPlanner.exe` into `MAVLinkInterface` (71 action methods, 716 call sites). The REA index already held 108,294 call edges for the main executable, so a cross-assembly graph is the remaining work, not the exe-level one.

## Not yet done

Unmodified `MissionPlanner.exe` start-up (it writes to the user's Mission Planner data directory and may contact the network), a scripted GUI harness, cross-assembly call graph, the NaN-upload crash reproduction, and everything in Phases 3 onward of the plan.
