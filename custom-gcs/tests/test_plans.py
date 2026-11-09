import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from customgcs import motors, vehicle  # noqa: E402


def copter_params(cls, typ):
    p = {'FRAME_CLASS': cls, 'FRAME_TYPE': typ}
    p.update({'SERVO%d_FUNCTION' % n: 32 + n for n in range(1, 9)})
    return p


def test_detect_copter_and_frames():
    info = vehicle.detect(copter_params(2, 1), mav_type=13)
    assert (info.kind, info.frame_class, info.frame_type) == ('copter', 2, 1)


def test_detect_heli_by_class():
    assert vehicle.detect({'FRAME_CLASS': 6, 'FRAME_TYPE': 1}, mav_type=2).kind == 'heli'


def test_detect_sub_by_frame_config():
    info = vehicle.detect({'FRAME_CONFIG': 2}, mav_type=12)
    assert (info.kind, info.frame_class, info.class_param) == ('sub', 2, 'FRAME_CONFIG')


def test_detect_quadplane_needs_q_enable():
    assert vehicle.detect({'Q_ENABLE': 1, 'Q_FRAME_CLASS': 1, 'Q_FRAME_TYPE': 1}, mav_type=1).kind == 'quadplane'
    assert vehicle.detect({'Q_ENABLE': 0, 'Q_FRAME_CLASS': 1, 'Q_FRAME_TYPE': 1}, mav_type=1).kind == 'plane'


def test_detect_rover_blimp_tracker():
    assert vehicle.detect({'FRAME_CLASS': 1}, mav_type=10).kind == 'rover'
    assert vehicle.detect({'FRAME_CLASS': 2}, mav_type=7).kind == 'blimp'
    assert vehicle.detect({}, mav_type=5).kind == 'tracker'


def test_motor_number_ranges():
    assert [motors.motor_number(f) for f in (33, 40, 82, 85, 160, 179, 70)] == [1, 8, 9, 12, 13, 32, None]


def test_copter_quad_plus_sequence_matches_sweep():
    p = copter_params(1, 0)
    steps = motors.plan(vehicle.detect(p, mav_type=2), p)
    assert [s.expect_outputs for s in steps] == [(3,), (1,), (4,), (2,)]      # the order the simulator moved in (Copter-Frame-Types-Trace.md)
    assert all(s.needs_disarmed and not s.needs_armed for s in steps)
    assert steps[0].params[0] == 1.0 and steps[3].params[0] == 4.0


def test_copter_hexa_x_sequence_matches_sweep():
    p = copter_params(2, 1)
    steps = motors.plan(vehicle.detect(p, mav_type=13), p)
    assert [s.expect_outputs[0] for s in steps] == [5, 1, 4, 6, 2, 3]


def test_y4_type_missing_from_mission_planner_file_is_planned():
    p = copter_params(1, 19)
    assert len(motors.plan(vehicle.detect(p, mav_type=2), p)) == 4


def test_quadplane_maps_motors_through_servo_functions():
    p = {'Q_ENABLE': 1, 'Q_FRAME_CLASS': 1, 'Q_FRAME_TYPE': 1}
    p.update({'SERVO%d_FUNCTION' % n: 28 + n for n in range(5, 9)})              # motors 1..4 on outputs 5..8
    steps = motors.plan(vehicle.detect(p, mav_type=1), p)
    assert [s.expect_outputs for s in steps] == [(5,), (8,), (6,), (7,)]


def test_unassigned_motor_expects_no_output():
    p = {'Q_ENABLE': 1, 'Q_FRAME_CLASS': 1, 'Q_FRAME_TYPE': 1, 'SERVO5_FUNCTION': 33, 'SERVO6_FUNCTION': 34}      # the quadplane-ice shape
    steps = motors.plan(vehicle.detect(p, mav_type=1), p)
    assert [s.expect_outputs for s in steps] == [(5,), (), (6,), ()]


def test_tri_class_uses_the_hand_transcribed_sequence():
    p = {'FRAME_CLASS': 7, 'FRAME_TYPE': 0, 'SERVO1_FUNCTION': 33, 'SERVO2_FUNCTION': 34, 'SERVO4_FUNCTION': 36, 'SERVO7_FUNCTION': 39}
    steps = motors.plan(vehicle.detect(p, mav_type=15), p)
    assert [s.expect_outputs for s in steps] == [(1,), (4,), (7,), (2,)]


def test_sub_is_zero_based_armed_and_repeated():
    p = {'FRAME_CONFIG': 1}
    p.update({'SERVO%d_FUNCTION' % n: 32 + n for n in range(1, 7)})
    steps = motors.plan(vehicle.detect(p, mav_type=12), p)
    assert [s.params[0] for s in steps] == [0, 1, 2, 3, 4, 5]
    assert [s.expect_outputs[0] for s in steps] == [1, 2, 3, 4, 5, 6]
    assert all(s.needs_armed and s.params[5] == 2.0 and s.repeat_every_s == 0.25 for s in steps)


def test_sub_eight_thruster_frame_without_servo8_motor_has_seven_steps():
    p = {'FRAME_CONFIG': 2}
    p.update({'SERVO%d_FUNCTION' % n: 32 + n for n in range(1, 8)})
    p['SERVO8_FUNCTION'] = 7                                                   # default Sub parameters (Sub-Frame-Types-Trace.md)
    assert len(motors.plan(vehicle.detect(p, mav_type=12), p)) == 7


def test_rover_skid_uses_left_and_right_outputs_and_has_no_main_sail():
    p = {'FRAME_CLASS': 1, 'SERVO1_FUNCTION': 73, 'SERVO3_FUNCTION': 74}
    steps = motors.plan(vehicle.detect(p, mav_type=10), p)
    assert [s.label for s in steps] == ['throttle', 'steering', 'throttle left', 'throttle right']
    assert [s.expect_outputs for s in steps] == [(), (), (1,), (3,)]


def test_scripted_matrix_class_is_unsupported_without_its_script():
    p = copter_params(15, 0)
    with pytest.raises(motors.Unsupported):
        motors.plan(vehicle.detect(p, mav_type=2), p)


def test_plane_and_blimp_are_unsupported():
    for params, mt in (({}, 1), ({'FRAME_CLASS': 1}, 7)):
        with pytest.raises(motors.Unsupported):
            motors.plan(vehicle.detect(params, mav_type=mt), params)
