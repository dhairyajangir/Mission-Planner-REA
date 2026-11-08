"""Map ArduCopter flight modes to the ArduPilot autotest tests whose NAMES refer to them, using the final per-test results.

The mapping below is by test name only (I did not read each test body), so a mode listed here means "a test named for this mode
passed", not "the mode is fully covered". Modes with no name-matched test are written with an empty tests column.

    python build-copter-mode-test-map.py            write coverage/copter-mode-test-map.csv and print a summary
    python build-copter-mode-test-map.py --apply    also append the result to the matching ap-mode:ArduCopter rows in coverage/claims.csv
"""
import csv
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL = os.path.join(ROOT, 'sitl-evidence', 'autotest', 'autotest-final.csv')
OUT = os.path.join(ROOT, 'coverage', 'copter-mode-test-map.csv')
CLAIMS = os.path.join(ROOT, 'coverage', 'claims.csv')

# mode row id suffix -> tests chosen by name
MODE_TESTS = {
    'mode_stabilize': ['StabilityPatch', 'AirModeStabZeroThrottle'],
    'mode_althold': ['ModeAltHold', 'ManualThrottleModeChange'],
    'mode_loiter': ['ModeLoiter', 'LoiterToAlt', 'LoiterFlowBrakeOvershoot', 'LoiterNoCompassYaw', 'GPSGlitchLoiter', 'GPSGlitchLoiter2'],
    'mode_poshold': ['PosHoldTakeOff', 'PosHoldDesiredAttitudeMonotonic'],
    'mode_brake': ['BrakeMode', 'BrakeZ', 'AUTO_LAND_TO_BRAKE'],
    'mode_circle': ['ModeCircle', 'CircleSpeed', 'SuperSimpleCircle', 'CircleManualControlEntryLeft', 'CircleManualControlEntryRight', 'CirclePilotRadiusZero'],
    'mode_guided': ['GuidedYawRate', 'GuidedModeThrust', 'GuidedSubModeChange', 'GuidedEKFLaneChange', 'GuidedForceArm', 'GuidedWeatherVane', 'PAUSE_CONTINUE_GUIDED', 'DO_CHANGE_SPEED_in_guided'],
    'mode_auto': ['CopterMission', 'AutoRTL', 'AutoContinueOnRCFailsafe', 'GPSGlitchAuto', 'LoweheiserAuto', 'mission_NAV_LOITER_TURNS'],
    'mode_rtl': ['RTLSpeed', 'RTLYaw', 'RTL_ALT_FINAL_M', 'RTL_TO_RALLY', 'RTLStoppingDistanceSpeed', 'MAV_CMD_NAV_RETURN_TO_LAUNCH'],
    'mode_smart_rtl': ['SMART_RTL', 'SMART_RTL_EnterLeave', 'SMART_RTL_Repeat', 'BatteryFailsafeTwoStageSmartRTL'],
    'mode_land': ['Landing', 'PrecisionLanding', 'AirModeLanding', 'FenceFloorEnabledLanding', 'MAV_CMD_NAV_VTOL_LAND'],
    'mode_flip': ['ModeFlip'],
    'mode_throw': ['ThrowMode', 'ThrowDoubleDrop', 'ThrowModeRPMMin'],
    'mode_flowhold': ['ModeFlowHold'],
    'mode_follow': ['ModeFollow', 'ModeFollow_with_FOLLOW_TARGET'],
    'mode_zigzag': ['ModeZigZag'],
    'mode_autotune': ['AutoTune', 'AutoTuneAux', 'AutoTuneSwitch', 'AutoTuneYawD'],
    'mode_avoid_adsb': ['AP_Avoidance'],
    # no test whose name refers to these modes in the 424-test Copter list:
    'mode_acro': [], 'mode_drift': [], 'mode_sport': [], 'mode_turtle': [], 'mode_systemid': [],
    'mode_guided_nogps': [], 'mode_autorotate': [],
}


def load_final():
    final = {}
    with open(FINAL, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['vehicle'] == 'Copter':
                final[row['test']] = row['final_result']
    return final


def main():
    final = load_final()
    rows = []
    for mode, tests in MODE_TESTS.items():
        missing = [t for t in tests if t not in final]
        if missing:
            sys.exit('test names not in the Copter results: %s (%s)' % (missing, mode))
        passed = [t for t in tests if final[t] == 'PASSED']
        failed = [t for t in tests if final[t] != 'PASSED']
        rows.append({'mode': mode, 'tests_named_for_mode': len(tests), 'passed': len(passed), 'failed': len(failed),
                     'passed_tests': ' '.join(passed), 'failed_tests': ' '.join(failed)})
    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, list(rows[0].keys()), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print('%-18s tests=%2d passed=%2d failed=%d %s' % (r['mode'], r['tests_named_for_mode'], r['passed'], r['failed'], r['failed_tests']))
    if '--apply' in sys.argv:
        apply_to_claims(rows)


def apply_to_claims(rows):
    by_mode = {r['mode']: r for r in rows}
    lines = open(CLAIMS, 'rb').read().decode('utf-8').split('\n')
    out, changed = [], 0
    for line in lines:
        key = line.split(',', 1)[0]
        if key.startswith('ap-mode:ArduCopter/'):
            mode = key.split('/', 1)[1]
            r = by_mode.get(mode)
            if r and 'copter-mode-test-map' not in line:
                fields = next(csv.reader([line]))
                fields[6] = fields[6] + ';coverage/copter-mode-test-map.csv;sitl-evidence/autotest/autotest-final.csv'
                if r['tests_named_for_mode']:
                    extra = ("ArduPilot's own Copter autotest has %d test(s) named for this mode, %d passed%s (name-matched, test bodies not read; see coverage/copter-mode-test-map.csv)."
                             % (r['tests_named_for_mode'], r['passed'], (', failed: ' + r['failed_tests']) if r['failed'] else ''))
                else:
                    extra = "ArduPilot's own Copter autotest has no test named for this mode."
                fields[7] = fields[7].rstrip() + ' ' + extra
                buf = io.StringIO()
                csv.writer(buf, lineterminator='').writerow(fields)
                line = buf.getvalue()
                changed += 1
        out.append(line)
    open(CLAIMS, 'wb').write('\n'.join(out).encode('utf-8'))
    print('claims rows updated:', changed)


if __name__ == '__main__':
    main()
