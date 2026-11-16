# ArduPilot Lua scripting trace

This is a selected trace of the supplied archive at commit `72b238201f5ea3b556e3809b2ec704fcf701474a`. Build options and vehicle configuration can change which paths are present.

## Initialization and configuration

`libraries/AP_Scripting/AP_Scripting.cpp:65` defines the scripting parameter group. Its `ENABLE` setting selects whether Lua scripts are enabled and is documented as requiring reboot; `VM_I_COUNT` controls the instruction count used to identify excessive execution, and `HEAP_SIZE` sets the scripting heap allocation. The source also exposes debug options, including one described as disabling a pre-arm check. These descriptions do not establish safe values for any aircraft.

`AP_Scripting::init` returns when scripting is disabled. When enabled and filesystem writing is compiled in, it attempts to create the script directory if that directory is enabled; it then starts a scripting thread and records a failure if thread creation fails (`AP_Scripting.cpp:219`). The thread creates a `lua_scripts` object using the configured instruction count and heap size, then calls its `run` method. If allocation fails it reports an error; after the backend stops, the thread releases several allocated resources and waits for a restart condition (`AP_Scripting.cpp:297`).

## Loading and execution

`lua_scripts::run` includes directory-loading calls for the configured script directory and ROMFS under applicable conditions (`libraries/AP_Scripting/lua_scripts.cpp:478`, `:545`, `:550`). The directory loader skips names starting with a dot and names that do not end in `.lua`, loads eligible files, and schedules successful loads (`:246`). `load_script` calls `luaL_loadfile`, reports syntax, memory and file errors, creates a per-script environment and records checksums when the filesystem CRC operation succeeds (`:162`).

The method named `create_sandbox` supplies a base environment, selected Lua libraries including `io` and `package`, and generated bindings (`:218`). The name of this method does not by itself establish a security boundary or describe the full authority exposed by those libraries and bindings. The scheduler installs a Lua instruction-count hook and calls `run_next_script` (`:320`, `:323`, `:614`); a complete execution, API-capability and error-recovery analysis remains open.

## Commands and remaining evidence

Where MAVLink scripting bindings are enabled, `AP_Scripting::handle_command_int_packet` denies the REPL start/stop commands shown in that switch, accepts stop and stop-and-restart, and returns unsupported for other cases (`AP_Scripting.cpp:275`). Pre-arm and checksum checks are implemented elsewhere in the same file and depend on settings and build options; their outcomes have not been exercised here.

## Local simulator observation

A disposable source-built Copter SITL instance used `SCR_ENABLE=1` and a synthetic `scripts/codex_probe.lua` that sent a numbered status message and rescheduled itself. A standalone MAVLink client sent ground-station heartbeats, read back `SCR_ENABLE=1`, and received three distinct script messages (`sitl-evidence/archive-lua-scripting-retry/results.json`). An earlier run without the client's ground-station heartbeat received no matching messages (`sitl-evidence/archive-lua-scripting/results.json`); the test does not isolate heartbeat delivery as the sole cause. Neither run exercised malformed scripts, instruction limits, stop/restart, checksum checks, or a physical controller.

A separate simulator run loaded the same healthy script and a second synthetic script that entered an infinite loop after an eight-second scheduled delay. The client observed `codex_limit.lua exceeded time limit` followed by a later message from the healthy script (`sitl-evidence/archive-lua-instruction-limit/results.json`). The source's instruction hook raises an error and `run_next_script` removes the offending script (`lua_scripts.cpp:62`, `:323`). This checks one instruction-limit event and subsequent activity from one other script, not all script failures, process isolation, or a security boundary.

A third run placed the same healthy script in the scripts directory but started with `SCR_ENABLE=1` and `SCR_DIR_DISABLE=2`. Both values were read back; the client received a directory-disabled status and no probe messages during a 15-second observation (`sitl-evidence/archive-lua-disabled-directory/results.json`). The enabled-directory comparison is a separate simulator run, not a controlled test of every source of script loading.

## Malformed-script fault injection: removed once, but the error is repeated on purpose, and feeds a pre-arm check

The instruction-limit removal path above was already confirmed, but a plain Lua runtime error (not a CPU-time timeout) was explicitly left untried. `research-tools/sitl-lua-script-error.py` (output `sitl-evidence/lua-script-error/`) set `SCR_ENABLE`=1 (the usual two-stage reboot) and loaded two scripts: a healthy one rescheduling itself every 2s (`CODEX_LUA_HEALTHY N`), and one calling `error("deliberate test failure from codex_error.lua")` on its very first call.

`lua_scripts.cpp`'s `lua_pcall()` failure path does call `remove_script()` immediately, as a first read of the source suggested - but that is not the whole story, and the first run's result (the same error repeating every 10.0s: t=1.8, 11.8, 21.8, 31.8s) looked at first like the script was somehow being reloaded and re-failing. It is not: the same function that prints the error also explicitly says, in its own comment, `"re-print the latest error message every 10 seconds 10 times"`, and separately, `"we do not clear the buffer after we have finished printing, this allows it to be used for a pre-arm check"`. The script fails once and is genuinely removed from the schedule; the *message* is what gets deliberately re-announced, specifically so a pilot watching the GCS doesn't miss a one-off scripting failure, and specifically so arming can be blocked on it. Both held up exactly as documented: at t=28.6s, a `"PreArm: Scripting: ./scripts/codex_error.lua:3: deliberate..."` message appeared, confirming the retained error does block arming.

Throughout, the healthy script's own 2s schedule was completely unaffected - 20 messages over the 40s watch, right on schedule - confirming one broken script does not disturb any other script, the scripting engine as a whole, or the vehicle.

Limits: one run, Copter only, simulator only; whether the pre-arm block clears once the broken script file is removed and the simulator rebooted (rather than just waiting out the 10-repeat/90s window) was not tested; only an `error()` call was tried, not other malformed-script shapes (bad return values, which the same function also handles with its own `remove_script()` calls, were read but not exercised).
