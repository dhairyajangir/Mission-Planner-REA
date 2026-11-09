import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytest = __import__('pytest')
pytest.importorskip('pymavlink')
from customgcs import link, motors  # noqa: E402

DO_MOTOR_TEST = 209


class FakeMav:
    def __init__(self, owner):
        self.owner = owner

    def command_long_send(self, *args):
        if args[2] == DO_MOTOR_TEST:
            self.owner.on_motor_test()


class FakeLink:
    """Rejects the first `reject` motor tests (ack result 4), then accepts and drives SERVO1."""
    target_system = target_component = 1

    def __init__(self, reject):
        self.reject, self.count, self.mav, self.queue = reject, 0, FakeMav(self), []

    def on_motor_test(self):
        self.count += 1
        accepted = self.count > self.reject
        self.queue.append(types.SimpleNamespace(get_type=lambda: 'COMMAND_ACK', command=DO_MOTOR_TEST, result=0 if accepted else 4))
        row = {'servo%d_raw' % i: (1900 if i == 1 and accepted else 1500) for i in range(1, 17)}
        self.queue.append(types.SimpleNamespace(get_type=lambda: 'SERVO_OUTPUT_RAW', **row))

    def recv_match(self, type=None, blocking=True, timeout=0.1):
        return self.queue.pop(0) if self.queue else None


STEP = motors.Step('throttle left', (0, 0, 40.0, 0.1, 0, 0, 0), (1,), False, True, None)


def test_rejected_motor_test_is_retried_until_accepted(monkeypatch):
    monkeypatch.setattr(link.time, 'sleep', lambda s: None)
    result, _ = link.run_step(FakeLink(reject=2), STEP, [1500] * 16, ready_timeout=30)
    assert result.ok and result.moved == (1,)
    assert 'accepted after' in result.note


def test_never_accepted_is_reported_as_mismatch(monkeypatch):
    monkeypatch.setattr(link.time, 'sleep', lambda s: None)
    result, _ = link.run_step(FakeLink(reject=10 ** 6), STEP, [1500] * 16, ready_timeout=0.5)
    assert not result.ok and result.note.startswith('rejected (ack result 4')
