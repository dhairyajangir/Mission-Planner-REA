# Photo geotagging (GeoRef) trace

Scope: how Mission Planner 1.3.83 matches photos to positions from a flight log, probed at library level with a synthetic DataFlash text log and empty `.jpg` files. No real photos or EXIF, telemetry (`.tlog`) or binary logs, vehicle, camera or GUI were used. The dialog, report/KML/GPX writing, JPEG EXIF writing (`WriteCoordinatesToImage`) and the `TRIG` mode were read or skipped but **not run**.

## Source path

- `GeoRef/georefimage.cs` is the dialog. `BUT_doit_Click` (`:140`) calls one of three modes on `Utilities/GeoRefImageBase.cs`: `doworkGPSOFFSET` (`:614`, match photo time to GPS fixes with a user offset), `doworkCAM` (`:739`, pair photos with `CAM` messages) or `doworkTRIG` (`:968`). `BUT_Geotagimages_Click` (`:268`) later writes coordinates into the JPEGs.
- `getPhotoTime` (`GeoRefImageBase.cs:54`) reads the EXIF "date taken" tag, cached by file name in the public `filedatecache`. The probe seeds that cache so files can be empty.
- `readGPSMsgInLog` (`:141`) builds a table keyed by UTC millisecond from `GPS` (or `GPS2`) messages with status 3 or better, plus the latest `ATT` and altitude values. `readCAMMsgInLog` (`:308`) does the same for `CAM` messages.
- `ToMilliseconds` (`:501`) subtracts the Unix epoch from a `DateTime` and ignores its `Kind`. EXIF times carry no time zone, so they are used **as if they were UTC**.
- `LookForLocation` (`:576`) looks for an exact key at `t + n` ms, then `t - n` ms, for n from 0 up to `offsettime / 2`.
- Log GPS times come from `DFLog.gpsTimeToTime` (`DFLog.cs:704`), whose GPS-to-UTC leap-second count is looked up for the **current** date. `GetTimeFromGps` (`GeoRefImageBase.cs:490`), used for `CAM` messages, has a fixed 17 s.
- `doworkGPSOFFSET` also writes `<log file>.xml` next to the log file.

## Library-level probe

`research-tools/GeoRefProbe.cs` builds a text log (GPS fixes every 200 ms at 10 m/s, `ATT`, `CAM` messages) and calls the compiled `GeoRefImageBase` from `mission-planner-isolated/` (the earlier data-redirected utility DLL; the geotagging code is unchanged). Photo times are derived from the true UTC of each log instant (GPS week 2300, 18 s leap seconds). Files: `coverage/golden/georef-results.csv`, `georef-messages.csv`, `georef-probe-output.txt`. Message order in `georef-messages.csv` varies between runs because photos are processed in parallel.

Observed:

- **Time bases differ by one second.** The same instant read through the GPS path came back as the true UTC time; through the `CAM` path (`GetTimeFromGps`) it came back 1,000 ms later. Position-matching in `GPSOFFSET` mode is unaffected by the `CAM` constant, but the times stored for `CAM`-matched pictures are one second off the GPS-matched ones. The leap-second lookup for the current date was not varied.
- **Camera clock.** With photo times equal to UTC, pictures match. With a camera set to UTC+5:30 and offset 0, both test photos were "NOT PROCESSED"; with the offset field set to 19,800 s they matched. There is no time-zone conversion.
- **Nearest-fix matching.** Photo 50 ms after a fix took that fix; 130 ms after took the next fix (70 ms later); exactly halfway (100 ms) took the later fix. There is no interpolation.
- **Search radius.** `doworkGPSOFFSET` passes 5000 to `LookForLocation`, which searches only half of that. Photos 2,400 ms and 2,499 ms after the last fix matched it; 2,500, 2,600 and 4,900 ms did not.
- **Misreported distance.** The "ms away" text prints the `Milliseconds` component of a time difference, not its total: a fix 2,400 ms away is reported as "-400 ms away", 2,499 as "-499 ms away".
- **`CAM` mode pairs by position, not time.** The sorted photos are paired with the `CAM` messages in order. With one photo missing from a run of eight `CAM` messages, the photos after the gap were paired with the wrong messages (photos 4 to 7 each got the message one position too early; the messages are 1.5 s apart). The only signal is a text line "CAM Msgs and Files discrepancy", after which every photo is reported as processed.
- **Minimum shutter interval.** Two `CAM` messages 0.3 s apart (limit 0.5 s) caused the earlier one to be dropped with a "Possible Shutter speed issue" line; four photos then took messages 2, 3 and 4 of the original series, and the fourth photo got none. The filter does not look at the photos.
- **`dropstart` and `dropend`** removed the first and last `CAM` messages as expected.
- **Side effect.** The GPS-offset run left `a.log.xml` beside the log file.

## Not established

Real EXIF parsing, `.tlog` and binary logs, `TRIG` mode, the altitude options, shutter-lag handling, `EstimateOffset`, the report, KML and GPX output, JPEG writing, and any GUI behaviour. The synthetic log uses a constant 5 Hz fix rate and a clean clock, so behaviour with real fix gaps, clock drift or duplicate timestamps is only inferred from the code.
