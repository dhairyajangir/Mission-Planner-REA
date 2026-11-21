# Missing camera time in a survey JPEG

Mission Planner 1.3.83's time-offset geotagging routine accepted one synthetic survey photo and skipped its twin after removal of the camera capture time. Both inputs were valid 32 × 24 JPEGs with the same decoded pixels, image description and filesystem modification time. The test began with an empty photo-time cache.

| Input | Observed camera time | Result |
| --- | --- | --- |
| nominal.jpg | 2024-06-15 17:30:00 | Matched at 0 ms. The output JPEG contained latitude −35.125°, longitude 149.25° and altitude 120 m. |
| missing-time.jpg | 0001-01-01 00:00:00 | The release reported “NOT PROCESSED. No GPS match in the log file.” This photo produced no tagged copy. |

The nominal JPEG carries EXIF DateTimeOriginal. The missing-time copy has neither DateTimeOriginal nor DateTimeDigitized. Both files' modification times were set to the instant of the middle telemetry fix. Leaving the camera clock unset therefore exposed the missing-tag handling while the other inputs stayed usable. [Input fixtures](inputs/) · [Captured release output](observation.txt) · [Output JPEG](nominal_geotag.jpg)

## Independent check

The synthetic telemetry log contains three timestamped GLOBAL_POSITION_INT records at 11:59:59, 12:00:00 and 12:00:01 UTC. The release displayed their reception times using the test host's UTC+05:30 clock. The control photo's unzoned camera time corresponds to 12:00:00 UTC. Reading that record's three signed integers and applying the specified units gives −35.125°, 149.25° and 120 m AMSL. Pillow independently read those values from the written JPEG, including the southern and eastern hemisphere references. The emitted image retained the nominal camera timestamp. [Results and hashes](result.json) · [Fixture generator](fixtures.py)

The executable exercised the same compiled library calls used by the dialog for GPS time-offset processing and writing a matched image. The altitude choice corresponds to AMSL with a zero base offset. The test used the original utility, telemetry and EXIF assemblies from the pinned portable ZIP. It used a temporary profile and called the local file methods directly. The older GeoRef probe seeded the date cache and supplied empty files. This run exercised the actual JPEG metadata reader with the camera-time field removed, the matching routine and the writer. The ledger's L3+fault criterion is met for this workflow. GUI interaction, report generation, and the CAM/TRIG modes were outside this run. [Prior probe](../GeoRef-Trace.md) · [Dialog source](../mission-planner-1.3.83-source/GeoRef/georefimage.cs) · [Library source](../mission-planner-1.3.83-source/ExtLibs/Utilities/GeoRefImageBase.cs)

## Replay

Run `python -B copter-photo-geotagging-study/verify.py --retained` to verify the recorded evidence with Python and Pillow on any host. This decodes the input and output JPEGs and the timestamped telemetry records, checks their hashes against the manifest, and checks the application transcript.

Run `python -B copter-photo-geotagging-study/verify.py` from the repository root. The replay uses Pillow, the Windows .NET Framework 4 compiler and a local timezone of UTC+05:30 for the survey date. It verifies the portable ZIP hash, extracts the release assemblies into a temporary directory, compiles the probe and compares the fresh output byte-for-byte with the retained JPEG. [Replay](verify.py) · [Probe](Probe.cs)
