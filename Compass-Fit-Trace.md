# Compass calibration fit trace

Scope: the numerical fit in Mission Planner 1.3.83's legacy, ground-station-side compass calibration (`MagCalib.cs`), probed with synthetic data. No vehicle, simulator, real magnetometer log or GUI was used. The data-collection and save code was read but **not run**. ArduPilot's own onboard calibration (`MAG_CAL_*` messages) is a separate path and was not examined.

## Source path

- `GCSViews/ConfigurationView/ConfigHWCompass.cs:259` starts `MagCalib.DoGUIMagCalib`; `:372` runs `MagCalib.ProcessLog` on a log.
- `ReceviedPacket` (`MagCalib.cs:189`) collects `RAW_IMU`, `SCALED_IMU2` and `SCALED_IMU3` magnetometer values, drops a sample once its 20-unit cell (`div`, `:174`) already holds more than three, and skips zero readings (x and y both zero for compass 1, any zero component for compasses 2 and 3).
- After collection `prd_DoWork` removes outliers (`RemoveOutliers`, `:793`), then calls `LeastSq` (`:1159`) once per compass. It requests the ellipsoid fit whenever the vehicle has a `COMPASS_DIA_X` parameter (`:774`).
- `LeastSq` fits a sphere (centre and radius) with the Levenberg-Marquardt routine from alglib. With `ellipsoid` set it runs two more fits that add three diagonal terms, then three off-diagonal terms, and returns nine values: offsets, diagonals, off-diagonals.
- `SaveOffsets` (`:1271`) disables `COMPASS_LEARN`, writes `COMPASS_OFS_X/Y/Z` and, when the result has more than five values and `COMPASS_DIA_X` exists, `COMPASS_DIA_*` and `COMPASS_ODI_*`. Without a connection it only shows the offsets. Read only; not run.

## Source observations

- `RemoveOutliers` sorts by distance from the **origin** (0, 0, 0) and drops the `n / 16` farthest samples (integer division). With raw magnetometer data the sphere is centred on the sensor bias, not the origin, so this removes one cap of the sphere rather than outliers.
- After the sphere fit, `LeastSq` sets the target radius `rad` to the **mean distance of the samples from the origin** (`:1172`, the fitted radius is commented out). The ellipsoid stages then fit to that radius.
- `sphere_ellipsoid_error` (`:1441`) creates the offsets as a zero vector (`:1444`, the parameter version is commented out). The offset values are therefore not part of the ellipsoid fit; the diagonal and off-diagonal terms are fitted to the raw, uncorrected samples.

## Library-level probe

`research-tools/MagCalibFitProbe.cs` calls the compiled `MagCalib.LeastSq` and, by reflection, the private `RemoveOutliers`, on synthetic samples: 400 points on a sphere of radius 500, optionally shifted, distorted per axis, restricted to a hemisphere, with Gaussian noise (standard deviation 5, fixed seed). It ran from `mission-planner-isolated/` (the earlier data-redirected utility DLL; the executable and `MagCalib` are unchanged from the portable release). The samples are in `coverage/golden/mag-fit-data.csv`, the results in `mag-fit-results.csv` and `mag-fit-outliers.csv`.

Correction quality is the standard deviation of the corrected field magnitude as a percentage of its mean, using `corrected = M * (raw + offsets)`. This is the order ArduPilot uses (`libraries/AP_Compass/AP_Compass_Backend.cpp:85` adds the offsets, `:102` applies the matrix). The percentage is calculated on the full, unfiltered samples.

| Case | Sphere | Ellipsoid | Sphere + outlier removal | Ellipsoid + outlier removal | Offset error (sphere / with removal) |
| --- | ---: | ---: | ---: | ---: | ---: |
| centred sphere, no noise | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 / 0.00 |
| offset (120, -80, 40), no noise | 0.00 | 7.23 | 0.00 | 5.68 | 0.00 / 0.00 |
| same, noise | 0.98 | 7.28 | 0.99 | 5.68 | 0.53 / 0.97 |
| offset (400, -300, 250), noise | 0.98 | 16.97 | 0.98 | 20.97 | 0.53 / 0.73 |
| hemisphere only, noise | 0.98 | 11.31 | 0.98 | 11.62 | 0.58 / 0.94 |
| axis scales (1.15, 0.9, 1.0), noise | 6.42 | 6.70 | 6.54 | 5.75 | 0.51 / 10.74 |

Observed:

- The sphere fit recovers the offsets (returned with the sign ArduPilot expects, so they are added to the raw reading) to within 0.6 units without outlier removal, in every case including the hemisphere.
- For samples that really are a shifted sphere, the ellipsoid result is **worse** than the sphere result. It returns diagonals near (0.92, 1.01, 1.07) and off-diagonals near (0.11, -0.05, 0.04) where the truth is (1, 1, 1) and (0, 0, 0). The offsets are identical to the sphere fit's. The error grows with the offset size (17 to 21 per cent with a 400-unit offset).
- For samples with a real per-axis distortion, the ellipsoid stage barely helps: 6.42 to 6.70 per cent without outlier removal, 6.54 to 5.75 with it. This is the only case in the table where it reduces the spread.
- The target radius `rad` was 514.9 for the 120-unit offset and 708.1 for the 400-unit offset, against a true radius of 500.
- `RemoveOutliers` removes 0 samples from a list of 15, 1 from 16 and 17, 2 from 32, 6 from 100 and 25 from 400. For the distorted, offset samples it moved the offset estimate by 10.7 units; for the other offset cases by 0.2 to 0.5.

These are properties of the original code on synthetic data. They do not show what a real vehicle's calibration produces. Whether `RAW_IMU` from current firmware carries offset-corrected values (which would change the premise of the "offsets are 0" comment in the collection code) was not tested.

## Not established

Behaviour with real magnetometer samples or logs, the collection filter, the save path, the dialog, interaction with ArduPilot's onboard calibration, and whether a current vehicle accepts the written parameters.
