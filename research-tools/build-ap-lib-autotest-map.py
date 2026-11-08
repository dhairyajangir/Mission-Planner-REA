"""Map ArduPilot libraries to the ArduPilot autotest tests whose NAMES refer to them, using the final per-test results of all vehicles.

The rules below are regular expressions over test names that I chose by reading the names (not the test bodies). A library listed here
means "an autotest named for this library passed (or failed)", not that the library is covered. Libraries with no matching test get no
row. Libraries that already have unit-test evidence keep their claim and are not changed.

    python build-ap-lib-autotest-map.py            write coverage/ap-lib-autotest-map.csv and print a summary
    python build-ap-lib-autotest-map.py --apply    also add claims rows for libraries that had no execution evidence
"""
import csv
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL = os.path.join(ROOT, 'sitl-evidence', 'autotest', 'autotest-final.csv')
MATRIX = os.path.join(ROOT, 'coverage', 'matrix.csv')
OUT = os.path.join(ROOT, 'coverage', 'ap-lib-autotest-map.csv')
CLAIMS = os.path.join(ROOT, 'coverage', 'claims.csv')

RULES = {
    'AC_AttitudeControl': r'ThrottleGainBoost|AirMode',
    'AC_AutoTune': r'AutoTune',
    'AC_Avoidance': r'^(?!AP_Avoidance).*Avoid',
    'AC_PrecLand': r'PrecisionLanding|PrecisionLoiter',
    'AC_Sprayer': r'Sprayer',
    'AC_WPNav': r'WPArcs|Spline|^WP_SPEED$|^DO_CHANGE_SPEED$',
    'AC_PID': r'^PIDTuning$',
    'AC_CustomControl': r'CustomController',
    'AP_AccelCal': r'AccelCal',
    'AP_AHRS': r'AHRS',
    'AP_AIS': r'^AIS',
    'AP_Arming': r'ArmFeatures|Prearm|PreArm|ParameterChecks|^NoArm|REQUIRE_LOCATION_FOR_ARMING|ArmSwitch|CompassHealthArming|BatteryMissing|ParameterValidation',
    'AP_Avoidance': r'^AP_Avoidance$',
    'AP_Beacon': r'Beacon',
    'AP_Button': r'^Button$',
    'AP_Camera': r'Camera',
    'AP_Compass': r'Compass|MagFail|FuseMag|SixCompass',
    'AP_CRSF': r'CRSF',
    'AP_DroneCAN': r'DroneCAN',
    'AP_ESC_Telem': r'ESC',
    'AP_FETtecOneWire': r'FETtec',
    'AP_FlashStorage': r'FlashStorage',
    'AP_Follow': r'Follow',
    'AP_Generator': r'^IE24$|RichenPower',
    'AP_Gripper': r'Gripper',
    'AP_IBus_Telem': r'^IBus$',
    'AP_InertialSensor': r'IMUConsistency|GyroFFT|Notches|VibrationFailsafe|VibrationCompensation',
    'AP_LeakDetector': r'Leak',
    'AP_Motors': r'MotorTest|MotorThrustHover|FlyEachFrame|SkidSteer|MotorBoatSkid',
    'AP_Mount': r'Mount',
    'AP_NavEKF2': r'^SIMCompare$',
    'AP_Networking': r'Networking',
    'AP_NMEA_Output': r'NMEAOutput',
    'AP_OpticalFlow': r'OpticalFlow',
    'AP_Proximity': r'Proximity|OBSTACLE_DISTANCE',
    'AP_Quicktune': r'Quicktune',
    'AP_Rally': r'Rally',
    'AP_Relay': r'^(?!MAVLink).*Relay',
    'AP_Scheduler': r'PerfInfo',
    'AP_ServoRelayEvents': r'ServoRelayEvents',
    'AP_SmartRTL': r'SMART_RTL',
    'AP_SurfaceDistance': r'Surf',
    'AP_Tuning': r'Ch6Tuning|DualTuningChannels',
    'AP_VisualOdom': r'VisoForYaw|BodyFrameOdom',
    'AP_WheelEncoder': r'WheelEncoders',
    'AP_Winch': r'DO_WINCH',
    'AR_WPNav': r'^DriveMission$|^DriveSquare$|^DriveRTL$|^AutoModeAccel',
    'AR_Motors': r'SkidSteer|MotorBoat',
    'RC_Channel': r'AuxSwitch|AuxFunctions|^RCOverrides|SetModesViaAuxSwitch|RCDuplicate|RCModeChannel',
    'SRV_Channel': r'DO_SET_SERVO|UndrivenServos|ServoRange',
}


# tests that did not pass for a documented reason that is not a regression (see Reverse-Engineering-Coverage.md, autotest rows)
KNOWN = {
    'Rover:NetworkingWebServerPPP': 'did not run: its own waf build failed in my build copy',
    'Copter:PeriphMultiUARTTunnel': 'did not run: its own AP_Periph waf build failed in my build copy',
    'Copter:SMART_RTL_Repeat': 'listed in ArduPilot disabled_tests(): loop-detection issue',
    'Copter:FlyMissionTwice': 'listed in ArduPilot disabled_tests(): PR 18561',
}


def annotate(names):
    return ' '.join(n + (' (' + KNOWN[n] + ')' if n in KNOWN else '') for n in names.split())


def main():
    final = []
    with open(FINAL, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            final.append((r['vehicle'], r['test'], r['final_result']))
    with open(MATRIX, newline='', encoding='utf-8') as f:
        need = {r['row_id'].split(':', 1)[1]: r['level'] for r in csv.DictReader(f) if r['area'] == 'ap-lib'}
    rows = []
    for lib, rx in RULES.items():
        if lib not in need:
            sys.exit('rule for a library that is not in the matrix: ' + lib)
        pat = re.compile(rx)      # case-sensitive: the names are CamelCase, case-insensitive matching over-matched (for example 'esc')
        hits = [(v, t, res) for v, t, res in final if pat.search(t)]
        if not hits:
            rows.append({'library': lib, 'level_before': need[lib], 'tests': 0, 'passed': 0, 'failed': 0, 'vehicles': '', 'passed_tests': '', 'failed_tests': ''})
            continue
        passed = [v + ':' + t for v, t, res in hits if res == 'PASSED']
        failed = [v + ':' + t for v, t, res in hits if res != 'PASSED']
        rows.append({'library': lib, 'level_before': need[lib], 'tests': len(hits), 'passed': len(passed), 'failed': len(failed),
                     'vehicles': ' '.join(sorted({v for v, _, _ in hits})), 'passed_tests': ' '.join(passed), 'failed_tests': ' '.join(failed)})
    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, list(rows[0].keys()), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    matched = [r for r in rows if r['tests']]
    print('rules: %d, libraries with at least one named test: %d, without: %s' % (len(rows), len(matched), [r['library'] for r in rows if not r['tests']]))
    for r in matched:
        print('%-22s before=L%s tests=%3d passed=%3d failed=%d [%s]' % (r['library'], r['level_before'], r['tests'], r['passed'], r['failed'], r['vehicles']))
    if '--apply' in sys.argv:
        apply_claims(matched, need)


def apply_claims(matched, need):
    text = open(CLAIMS, 'rb').read().decode('utf-8')
    existing = {line.split(',', 1)[0] for line in text.split('\n') if line}
    if not text.endswith('\n'):
        text += '\n'
    added = 0
    for r in matched:
        key = 'ap-lib:' + r['library']
        if key in existing or need[r['library']] == '3':
            continue
        note = ("ArduPilot's own autotests (Blimp, Sub, AntennaTracker, Rover, Copter, disposable simulators, default debug build) include %d test(s) whose names refer to this library, %d passed%s. "
                "Matched by test name only (test bodies not read), so this shows the library is exercised by at least those scenarios, not how much of it; see coverage/ap-lib-autotest-map.csv."
                % (r['tests'], r['passed'], (', did not pass: ' + annotate(r['failed_tests'])) if r['failed'] else ''))
        buf = io.StringIO()
        csv.writer(buf, lineterminator='').writerow([key, '3', '', 'none', '', 'partial',
                                                     'coverage/ap-lib-autotest-map.csv;sitl-evidence/autotest/autotest-final.csv;sitl-evidence/autotest/autotest-results.csv', note])
        text += buf.getvalue() + '\n'
        added += 1
    open(CLAIMS, 'wb').write(text.encode('utf-8'))
    print('claims rows added:', added)


if __name__ == '__main__':
    main()
