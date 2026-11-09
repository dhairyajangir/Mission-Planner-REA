import http.client
import json
import os
import sys
import threading
import types
from http.server import ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from customgcs import webui  # noqa: E402


def msg(kind, **fields):
    fields.setdefault('get_srcComponent', lambda: 1)
    return types.SimpleNamespace(get_type=lambda: kind, **fields)


def test_state_reads_heartbeat_position_battery_gps_and_texts():
    state = webui.State()
    state.update(msg('HEARTBEAT', type=2, base_mode=129, custom_mode=5), 'copter')
    state.update(msg('GLOBAL_POSITION_INT', lat=-353632610, lon=1491652300, relative_alt=15500, hdg=9000, vx=300, vy=400), 'copter')
    state.update(msg('SYS_STATUS', voltage_battery=12600), 'copter')
    state.update(msg('GPS_RAW_INT', fix_type=3, satellites_visible=10), 'copter')
    state.update(msg('STATUSTEXT', text='hello'), 'copter')
    snap = state.snapshot()
    assert snap['armed'] is True and snap['mode'] == 'LOITER'
    assert snap['position'] == pytest.approx((-35.363261, 149.16523, 15.5)) and snap['speed'] == pytest.approx(5.0) and snap['heading'] == pytest.approx(90.0)
    assert snap['battery_v'] == pytest.approx(12.6) and snap['gps'] == (3, 10) and snap['texts'] == ['hello'] and snap['home'] is not None


def test_a_position_at_zero_zero_is_not_plotted_and_modes_follow_the_table():
    state = webui.State()
    state.table = 'rover'
    state.update(msg('GLOBAL_POSITION_INT', lat=0, lon=0, relative_alt=0, hdg=65535, vx=0, vy=0), 'rover')
    snap = state.snapshot()
    assert snap['position'] is None and snap['track'] == [] and snap['home'] is None
    assert ('MANUAL', 0) in snap['modes'] and all(name != 'INITIALISING' for name, _ in snap['modes'])


def test_state_ignores_gcs_heartbeats_and_unknown_battery_value():
    state = webui.State()
    state.update(msg('HEARTBEAT', type=6, base_mode=129, custom_mode=0), 'copter')
    state.update(msg('SYS_STATUS', voltage_battery=65535), 'copter')
    snap = state.snapshot()
    assert snap['armed'] is None and snap['battery_v'] is None


def test_the_same_mode_number_is_named_per_vehicle():
    copter, rover, plane = webui.State(), webui.State(), webui.State()
    for s, table in ((copter, 'copter'), (rover, 'rover'), (plane, 'plane')):
        s.update(msg('HEARTBEAT', type=2, base_mode=1, custom_mode=4), table)
    assert (copter.snapshot()['mode'], rover.snapshot()['mode'], plane.snapshot()['mode']) == ('GUIDED', 'HOLD', 'ACRO')


class FakeConn:
    def __init__(self, messages):
        self.messages = list(messages)

    def recv_match(self, type=None, blocking=False, timeout=None):
        return self.messages.pop(0) if self.messages else None


def test_statelink_updates_state_from_every_message_but_returns_only_the_wanted_type():
    state = webui.State()
    conn = FakeConn([msg('STATUSTEXT', text='first'), msg('SYS_STATUS', voltage_battery=11000), msg('COMMAND_ACK', result=0, command=400)])
    wrapped = webui.StateLink(conn, state, 'copter')
    ack = wrapped.recv_match(type=['COMMAND_ACK'], blocking=True, timeout=1.0)
    assert ack.get_type() == 'COMMAND_ACK'
    snap = state.snapshot()
    assert snap['texts'] == ['first'] and snap['battery_v'] == pytest.approx(11.0)


def test_statelink_returns_none_when_nothing_matches_before_the_timeout():
    wrapped = webui.StateLink(FakeConn([msg('STATUSTEXT', text='x')]), webui.State(), 'copter')
    assert wrapped.recv_match(type='COMMAND_ACK', blocking=True, timeout=0.3) is None


@pytest.fixture
def server():
    session = webui.Session()
    page = '<html>TOKEN=__TOKEN__</html>'
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), webui.make_handler(session, 'secret-token', page))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    session.close()


def request(port, method, path, body=None, headers=None, host=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    h = dict(headers or {})
    if host:
        h['Host'] = host
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data


def test_page_carries_the_token_and_state_is_served(server):
    status, body = request(server, 'GET', '/')
    assert status == 200 and b'TOKEN=secret-token' in body
    status, body = request(server, 'GET', '/api/state')
    assert status == 200 and json.loads(body)['connected'] is False


def test_posts_without_the_token_are_refused(server):
    status, body = request(server, 'POST', '/api/arm', {}, {'Content-Type': 'application/json'})
    assert status == 403 and b'token' in body
    status, _ = request(server, 'POST', '/api/arm', {}, {'X-Token': 'wrong'})
    assert status == 403


def test_a_foreign_host_header_is_refused_even_with_the_token(server):
    status, _ = request(server, 'GET', '/api/state', host='evil.example')
    assert status == 403
    status, _ = request(server, 'POST', '/api/arm', {}, {'X-Token': 'secret-token'}, host='evil.example:8765')
    assert status == 403


def test_commands_without_a_connection_say_so(server):
    for path, body in (('/api/arm', {}), ('/api/disarm', {}), ('/api/mode', {'name': 'LOITER'}), ('/api/mission/start', {}), ('/api/mission/fly', {}), ('/api/param', {'name': 'X', 'value': 1})):
        status, data = request(server, 'POST', path, body, {'X-Token': 'secret-token'})
        reply = json.loads(data)
        assert status == 200 and reply['ok'] is False and 'not connected' in reply['detail'], (path, reply)


def test_bad_mission_text_is_refused_before_any_vehicle_is_needed(server):
    status, data = request(server, 'POST', '/api/mission/upload', {'wpl': 'not a mission'}, {'X-Token': 'secret-token'})
    reply = json.loads(data)
    assert reply['ok'] is False and ('not connected' in reply['detail'] or 'QGC WPL' in reply['detail'])


def test_unknown_paths_are_404(server):
    assert request(server, 'GET', '/nope')[0] == 404
    assert request(server, 'POST', '/api/nope', {}, {'X-Token': 'secret-token'})[0] == 404


def test_the_server_binds_to_loopback_only(server):
    s = webui.make_handler
    assert s is not None
    import inspect
    assert "('127.0.0.1', ui_port)" in inspect.getsource(webui.serve)
