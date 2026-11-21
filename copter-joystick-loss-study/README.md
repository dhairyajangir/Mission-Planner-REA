# Joystick device loss on a closed link

The Mission Planner 1.3.83 joystick worker retained its last mapped channel values when a fake joystick became invalid. After a separate explicit clear, the joystick was disabled and both observed channels were zero.

| Observation | Enabled | Channel 1 | Channel 3 |
| --- | --- | ---: | ---: |
| Device started | True | 2000 | 1000 |
| Worker observed device loss after channel 1 moved | True | 1000 | 1000 |
| Explicit clear | False | 0 | 0 |

The fixture waits until the original worker checks the invalid device. An earlier timing-based capture gave differing results across a pair of runs. The synchronized capture uses observed state changes and records the same result in two fresh processes. These numbers describe the ground station's in-memory overrides on a closed link. The experiment did not measure transmitted packets, receiver behavior or aircraft response.

Run `python -B copter-joystick-loss-study/replay.py --replay` from the research repository on Windows with the release archive, extracted assemblies and .NET Framework compiler available. Each process also reproduces the 1,092 archived mapping vectors. The default invocation checks the retained records and release assembly hashes without launching the worker.
