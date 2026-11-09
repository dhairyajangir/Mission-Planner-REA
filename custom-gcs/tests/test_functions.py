import math
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from customgcs import flight, mission, params  # noqa: E402


# ---- parameters

def test_float32_comparison_ignores_representation():
    assert params.same(0.1, 0.10000000149011612)
    assert not params.same(0.1, 0.2)
    assert params.same(float('nan'), float('nan'))


def test_diff_lists_changed_and_missing_sorted():
    current = {'A': 1.0, 'B': 2.0, 'C': 3.0}
    wanted = {'C': 3.0, 'B': 5.0, 'Z': 1.0}
    assert [(c.name, c.old, c.new) for c in params.diff(current, wanted)] == [('B', 2.0, 5.0), ('Z', None, 1.0)]


def test_dump_and_load_round_trip_float32_values():
    original = {'WPNAV_SPEED': 500.0, 'ATC_ANG_RLL_P': 4.5, 'X': 0.1, 'NEG': -3.25}
    loaded = params.loads(params.dumps(original))
    assert params.diff(loaded, original) == [] and params.diff(original, loaded) == []


def test_load_accepts_common_separators_and_comments():
    assert params.loads('# c\nA,1\nB 2.5\nC\t3 # trailing\n\n') == {'A': 1.0, 'B': 2.5, 'C': 3.0}


@pytest.mark.parametrize('text,reason', [('A,1,2\n', 'line 1'), ('A,xyz\n', 'not a number'), ('A,nan\n', 'non-finite'), ('A,inf\n', 'non-finite'), ('A,1\nA,2\n', 'twice')])
def test_load_rejects_bad_lines_with_a_reason(text, reason):
    with pytest.raises(ValueError, match=reason):
        params.loads(text)


def test_vehicle_maintained_parameters_are_volatile_and_protected():
    for name in ('COMPASS_DEC', 'MIS_TOTAL', 'BARO1_GND_PRESS', 'BARO2_GND_TEMP', 'BARO_GND_PRESS'):
        assert params.volatile(name) and params.protected(name)
    assert not params.volatile('COMPASS_DEC_X') and not params.volatile('RTL_ALT_M')


def test_protected_names():
    assert params.protected('SERIAL1_BAUD') and params.protected('SYSID_THISMAV') and params.protected('STAT_RUNTIME')
    assert not params.protected('WPNAV_SPEED')


class EchoLink:
    """Echoes PARAM_SET back as PARAM_VALUE; names in `keep` keep their old value."""
    target_system = target_component = 1

    def __init__(self, store, keep=()):
        self.store, self.keep, self.queue = dict(store), set(keep), []
        self.mav = types.SimpleNamespace(param_set_send=self.param_set)

    def param_set(self, ts, tc, name, value, kind):
        name = name.decode()
        if name not in self.keep:
            self.store[name] = value
        self.queue.append(types.SimpleNamespace(param_id=name, param_value=self.store.get(name, 0.0)))

    def recv_match(self, type=None, blocking=True, timeout=0.1):
        return self.queue.pop(0) if self.queue else None


def test_restore_writes_only_differences_and_verifies():
    link = EchoLink({'A': 1.0, 'B': 2.0, 'SERIAL1_BAUD': 57.0})
    wanted = {'A': 1.0, 'B': 9.0, 'SERIAL1_BAUD': 115.0}
    report = params.restore(link, wanted, lambda l: dict(l.store), armed=False)
    assert [c.name for c in report.planned] == ['B'] and report.skipped_protected == ('SERIAL1_BAUD',)
    assert all(r.ok for r in report.results) and report.remaining == ()
    assert link.store['SERIAL1_BAUD'] == 57.0


def test_restore_reports_a_parameter_the_vehicle_refuses_to_change():
    link = EchoLink({'B': 2.0}, keep=('B',))
    report = params.restore(link, {'B': 9.0}, lambda l: dict(l.store), armed=False)
    assert not report.results[0].ok and [c.name for c in report.remaining] == ['B']


def test_restore_refuses_when_armed_and_dry_run_writes_nothing():
    link = EchoLink({'B': 2.0})
    with pytest.raises(RuntimeError, match='armed'):
        params.restore(link, {'B': 9.0}, lambda l: dict(l.store), armed=True)
    report = params.restore(link, {'B': 9.0}, lambda l: dict(l.store), armed=False, dry_run=True)
    assert link.store['B'] == 2.0 and [c.name for c in report.planned] == ['B']


# ---- flight modes

def test_mode_table_comes_from_the_source_and_leaves_out_auto_rtl():
    modes = flight.copter_modes()
    assert modes['STABILIZE'] == 0 and modes['LOITER'] == 5 and modes['RTL'] == 6 and modes['LAND'] == 9 and modes['TURTLE'] == 28
    assert 'AUTO_RTL' not in modes and len(modes) == 25
    assert flight.mode_name(27) == 'AUTO_RTL' and flight.mode_name(8).startswith('UNKNOWN')


def test_unknown_mode_name_is_rejected_before_anything_is_sent():
    sent = []
    link = types.SimpleNamespace(mav=types.SimpleNamespace(command_long_send=lambda *a: sent.append(a)), target_system=1, target_component=1)
    with pytest.raises(KeyError):
        flight.set_mode(link, 'SPACESHIP')
    assert sent == []


def test_armed_flag():
    assert flight.is_armed(types.SimpleNamespace(base_mode=129)) and not flight.is_armed(types.SimpleNamespace(base_mode=1))


# ---- missions

def item(seq, x=-35.36, y=149.16, z=20.0, command=16, frame=3):
    return mission.Item(seq, frame, command, 0, 1, 0.0, 0.0, 0.0, 0.0, x, y, z)


@pytest.mark.parametrize('bad', [item(1, x=float('nan')), item(1, y=float('inf')), item(1, x=91.0), item(1, y=-181.0), item(1, z=float('nan'))])
def test_unsafe_items_are_rejected_before_sending(bad):
    with pytest.raises(ValueError):
        mission.check(bad)


def test_sequences_must_run_from_zero():
    with pytest.raises(ValueError, match='sequence'):
        mission.check_all([item(0), item(2)])


def test_wpl_round_trip_and_strict_reader():
    items = [item(0, 0.0, 0.0, 0.0), item(1, command=22, z=10.0), item(2, x=-35.3612, y=149.1655, z=25.5)]
    assert mission.loads_wpl(mission.dumps_wpl(items)) == items
    with pytest.raises(ValueError, match='expected 12 fields'):
        mission.loads_wpl('QGC WPL 110\n0\t1\t0\t16\t0\t0\t0\t0\t0\t0\t0\n')            # eleven fields: Mission Planner's reader would skip this row silently
    with pytest.raises(ValueError, match='not a QGC WPL'):
        mission.loads_wpl('hello\n')
    with pytest.raises(ValueError):
        mission.loads_wpl('QGC WPL 110\n0\t1\t0\t16\t0\t0\t0\t0\tnan\t0\t0\t1\n')


def test_verify_compares_from_item_one_with_tolerance():
    sent = [item(0, 0, 0, 0), item(1), item(2, x=-35.3612)]
    same = [item(0, 1, 1, 1), item(1, x=-35.36 + 1e-8), item(2, x=-35.3612)]
    assert mission.verify(sent, same) == []
    other = [item(0), item(1, z=21.0), item(2, x=-35.3612)]
    assert 'item 1 z' in mission.verify(sent, other)[0]
    assert 'item count' in mission.verify(sent, same[:2])[0]
    rtl_sent = [item(0), mission.Item(1, 3, 20, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0)]
    rtl_back = [item(0), mission.Item(1, 0, 20, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0)]
    assert mission.verify(rtl_sent, rtl_back) == []          # frame is not compared for an item without a location
    wp_back = [item(0), item(1, frame=0)]
    assert 'item 1 frame' in mission.verify([item(0), item(1)], wp_back)[0]


# ---- command line guard

def test_state_changing_commands_refuse_a_remote_host(capsys):
    from customgcs import __main__ as cli
    for command in ('arm', 'disarm', 'mode', 'params-restore', 'mission-upload', 'mission-clear', 'motor-test'):
        assert cli.main([command, '--host', '192.168.1.20']) == 3
    assert 'refusing' in capsys.readouterr().out


def test_modes_listing_needs_no_vehicle(capsys):
    from customgcs import __main__ as cli
    assert cli.main(['modes']) == 0
    assert ' 5 LOITER' in capsys.readouterr().out
