# Legacy compass fit with level-only calibration samples

The original Mission Planner 1.3.83 sphere fitter returned a vertical correction of **−6.23** for level-only readings generated with a known correction of **−150**. The fitted radius was **520.26** for a true field magnitude of **500**. Nevertheless, the fitted sphere matched every one of the 122 calibration readings to within 0.0001 synthetic field units. [Measured results](fit-results.json)

| Synthetic readings | Count | Fitted vertical correction | Fitted radius |
| --- | ---: | ---: | ---: |
| Directions spanning a sphere | 122 | −150.00 | 500.00 |
| Level rotation in one plane | 122 | −6.23 | 520.26 |
| Same level rotation with the last two samples replaced by opposite poles | 122 | −150.00 | 500.00 |

All three cases used a field of 500 and sensor bias (+120, −80, +150). For the level rotation, every sample has the same vertical coordinate. A sphere centred anywhere on the ring's perpendicular axis can pass through that ring if its radius changes accordingly. Applying the level-only fit to two withheld vertical readings gave magnitudes of **356.23** and **643.77**. This explains how a small fitting error on the observed orientations can coexist with a large error elsewhere. The opposite poles provide the missing vertical variation in this synthetic control. [Fixture and original method call](OrientationProbe.cs) · [Independent calculation](verify.py)

The probe invoked the compiled `MissionPlanner.MagCalib.LeastSq(samples, false)` in two fresh Windows .NET Framework processes. All loaded release files matched the original ZIP; the result records the method token, module identity and file hashes. The experiment exercised the legacy ground-station sphere fit in isolation. It did not exercise the collection UI, onboard calibration, parameter saving or a physical sensor. [Earlier fit investigation](../Compass-Fit-Trace.md)

On Windows with the original portable release present, `python -B copter-compass-orientation-study/replay.py --check` recompiles and reruns the calculation twice. `python -B copter-compass-orientation-study/verify.py` checks the retained result on any Python 3.8+ host.
