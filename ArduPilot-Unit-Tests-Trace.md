# ArduPilot C++ unit tests (waf `tests`, board linux)

Scope: the unit tests that ship in the supplied snapshot (commit `72b238201f5ea3b556e3809b2ec704fcf701474a`), built and run on this machine in the pinned snapshot copy in the `Ubuntu-E` WSL distribution with `research-tools/run-unit-tests.sh` (`./waf configure --board linux`, `./waf tests -j6`, then every `build/linux/tests/*` binary with a 300 s limit). This is separate from the simulator autotests: it tests library code directly, with no vehicle.

Result (`sitl-evidence/unit-tests/`): the configure and the build succeeded (build 14 min 56 s); 70 test binaries were built and **all 70 exited with status 0**. `coverage/ap-lib-unit-tests.csv` lists, per library, the binaries and the number of gtest cases they report; the binaries come from `libraries/<lib>/tests/` of 24 libraries (`research-tools/build-ap-lib-unit-test-map.py`). Of the gtest cases, one is reported as skipped by the test itself: `AP_GSOF.packet1` (4 of 5 cases passed, the binary exits 0).

| Library | Binaries | gtest cases |
|---|---:|---:|
| AP_Math | 18 | 698 |
| AP_Common | 13 | 82 |
| AP_HAL | 3 | 85 |
| AP_ExternalAHRS | 1 | 17 |
| Filter | 3 | 13 |
| AP_Filesystem | 2 | 13 |
| AP_Param | 3 | 11 |
| AP_RTC | 1 | 10 |
| AP_CSVReader | 1 | 7 |
| AP_Baro | 1 | 6 |
| AP_GSOF | 1 | 5 (1 skipped) |
| AP_RCProtocol | 2 | 4 |
| AP_HAL_Linux | 1 | 4 |
| AP_Declination | 2 | 3 |
| AP_NavEKF | 1 | 3 |
| AP_ADSB, AP_BattMonitor, AP_MSP | 1 each | 2 each |
| AP_RangeFinder, AP_GPS, AP_GyroFFT, AP_JSButton, AP_MultiHeap, AP_OLC | 1 each | 1 each |

Eight binaries (`test_better_stream`, `test_data_rate_limit`, `test_dsm`, `test_getopt`, `test_own_ptr`, `test_replace`, `test_ringbuffer`, `test_sparse_endian`) have no `libraries/*/tests/<name>.cpp` source of that name, so they are not attributed to a library in the table (their sources live elsewhere or under another file name); they exit 0 and are counted in the 70.

These tests exercise a library's own functions (math, parsing, filters, parameter handling and so on); they say nothing about how a library behaves in a vehicle. 23 of the 24 libraries already had execution evidence from earlier unit-test work in this project; this run repeats it on the current build and adds `AP_HAL_Linux`, which was only at level 1.

## Not covered

The libraries that have no unit tests in the snapshot at all, and the unit tests that need other boards or options (this run built only the default `tests` target for the linux board).
