"""Check the integrity and scope of currently captured research evidence."""
import hashlib
import base64
import binascii
import json
import math
import re
from pathlib import Path
import sqlite3
import zlib
from env_paths import INTEGRATION_DIR

root = Path(__file__).resolve().parent.parent
checks = []

def check(name, condition, detail):
    checks.append({'name': name, 'passed': bool(condition), 'detail': detail})

prov = json.loads((root / 'ardupilot-source/archive-provenance.json').read_text())
check('archive blobs match upstream tree',
      prov['zip_files'] == prov['upstream_blob_count'] == prov['matched_blobs'] == 8461 and
      not prov['extra_zip_paths'] and not prov['missing_upstream_paths'] and not prov['mismatches'] and
      prov['candidate_commit_from_zip_comment'] == prov['git_tree_response_sha'],
      'Does not by itself validate extracted source files or a build.')
sub = json.loads((root / 'ardupilot-source/extracted-submodule-verification.json').read_text())
check('pinned dependency blob readback', len(sub) == 16 and
      sum(x['expected_blobs'] for x in sub) == 16900 and
      all(not x['missing'] and not x['mismatches'] for x in sub),
      'Checks expected bytes; Windows extraction does not recreate two symbolic links.')
exe = root / 'mission-planner-portable/MissionPlanner.exe'
sha = hashlib.sha256(exe.read_bytes()).hexdigest()
coverage = json.loads((root / 'mission-planner-binary-evidence/rea-main-coverage.json').read_text())
check('main PE REA type coverage', sha == coverage['assembly_sha256'] and
      coverage['inventory_typedefs_excluding_module'] == coverage['observed_inventory_typedefs'] == 890 and
      coverage['unique_method_tokens'] == 6050 and not coverage['missing_types'] and not coverage['issues'],
      'Static metadata coverage is not behavioral coverage.')
for name in ('rea-main-index.sqlite', 'rea-supporting-index.sqlite'):
    db = sqlite3.connect('file:' + str(root / 'mission-planner-binary-evidence' / name) + '?mode=ro', uri=True)
    outcome = db.execute('PRAGMA integrity_check').fetchone()[0]
    db.close()
    check(name + ' integrity', outcome == 'ok', outcome)
extended_root = root / 'mission-planner-binary-evidence/extended-assembly-members'
extended = json.loads((extended_root / 'manifest.json').read_text())
extended_db = sqlite3.connect('file:' + str(root / 'mission-planner-binary-evidence/rea-extended-index.sqlite') + '?mode=ro', uri=True)
extended_counts = tuple(extended_db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                        for table in ('assemblies', 'types', 'methods', 'calls'))
extended_integrity = extended_db.execute('PRAGMA integrity_check').fetchone()[0]
extended_db.close()
check('REA extended managed member inventory', len(extended['requested']) == len(extended['results']) == 16 and
      set(extended['requested']) == {x['file'] for x in extended['results']} and
      all(x['exit_code'] == 0 and x['digest_matches'] and x['coverage']['state'] == 'complete' and
          hashlib.sha256((root / 'mission-planner-portable' / x['file']).read_bytes()).hexdigest() == x['sha256'] and
          json.loads((extended_root / x['evidence']).read_text())['subject']['digest']['sha256'] == x['sha256']
          for x in extended['results']) and extended_counts == (16, 845, 5112, 22934) and extended_integrity == 'ok',
      'Selected plugin, device and utility member metadata only; not behavior or whole-distribution coverage.')
remaining = root / 'mission-planner-binary-evidence/remaining-managed-members'
remaining_manifest = json.loads((remaining / 'manifest.json').read_text())
accord_entry = next(x for x in remaining_manifest['results'] if x['path'] == 'Accord.Statistics.dll')
import gzip
with gzip.open(remaining / accord_entry['evidence'], 'rt', encoding='utf-8') as stream:
    accord_whole = json.load(stream)
accord_cecil = [line.split('\t') for line in (remaining / 'accord-statistics-cecil-types.tsv').read_text().splitlines()]
accord_target = json.loads((remaining / 'accord-circular-targeted.json').read_text())
check('partial Accord metadata and targeted REA recovery',
      accord_entry['coverage']['state'] == 'partial' and
      {int(x['token'], 16) for x in accord_whole['normalized_result']['types']} ==
      {int(row[0], 16) for row in accord_cecil} and len(accord_cecil) == 680 and
      sum(int(row[4]) for row in accord_cecil) == 7812 and
      accord_target['subject']['digest']['sha256'] == accord_entry['sha256'] and
      accord_target['normalized_result']['coverage']['state'] == 'complete' and
      not accord_target['normalized_result']['selection']['unmatched_type_names'] and
      len(accord_target['normalized_result']['methods']) == 45,
      'Whole-assembly REA result remains partial; matching type tokens and one targeted type do not prove full method coverage.')
for dirname, expected in (('all-managed-identities', 260), ('native-exports', 70)):
    data = json.loads((root / 'mission-planner-binary-evidence' / dirname / 'manifest.json').read_text())
    check(dirname + ' inventory', data['requested'] == len(data['results']) == expected and
          all(x['status'] == 'complete' for x in data['results']),
          'Identity or export-table inspection only; not all internal behavior.')
references = root / 'mission-planner-binary-evidence/managed-references'
ref_manifest = json.loads((references / 'manifest.json').read_text())
graph_path = root / 'mission-planner-binary-evidence/managed-reference-graph.sqlite'
graph_summary = json.loads((root / 'mission-planner-binary-evidence/managed-reference-graph-summary.json').read_text())
graph = sqlite3.connect('file:' + str(graph_path) + '?mode=ro', uri=True)
graph_counts = (graph.execute('SELECT COUNT(*) FROM assemblies').fetchone()[0],
                graph.execute('SELECT COUNT(*) FROM assembly_references').fetchone()[0],
                graph.execute('SELECT COUNT(*) FROM exact_candidates').fetchone()[0])
graph_integrity = graph.execute('PRAGMA integrity_check').fetchone()[0]
graph.close()
check('REA managed declared-reference graph', ref_manifest['requested'] == len(ref_manifest['results']) == 260 and
      all(x['status'] == 'complete' for x in ref_manifest['results']) and graph_counts == (260, 1063, 402) and
      graph_integrity == 'ok' and
      hashlib.sha256(graph_path.read_bytes()).hexdigest() == graph_summary['sqlite_sha256'] and
      hashlib.sha256((references / 'manifest.json').read_bytes()).hexdigest() == graph_summary['manifest_sha256'],
      'Declared identities only; no CLR binding, redirects, or dynamic loads resolved.')
boundaries = root / 'mission-planner-binary-evidence/managed-native-boundaries'
boundary_manifest = json.loads((boundaries / 'manifest.json').read_text())
check('managed native boundary evidence', len(boundary_manifest) == 2 and
      all(entry['exit_code'] == 0 and entry['digest_matches'] and entry['coverage'] == 'complete' and
          hashlib.sha256((root / 'mission-planner-portable' / entry['file']).read_bytes()).hexdigest() == entry['sha256']
          for entry in boundary_manifest),
      'Managed import declarations only; native exports and runtime behavior are not established by this check.')
firmware_run = root / 'sitl-evidence/firmware-parser-probe'
firmware_result = json.loads((firmware_run / 'verification.json').read_text())
firmware_log = (firmware_run / 'probe.log').read_text(errors='replace')
firmware_cases = {row['file']: row for row in firmware_result['checks']}
check('synthetic firmware parser size observations', firmware_result['passed'] and
      (firmware_run / 'exit.txt').read_text().strip() == '0' and len(firmware_cases) == 5 and
      all(row['passed'] and hashlib.sha256((firmware_run / row['file']).read_bytes()).hexdigest() == row['sha256']
          for row in firmware_cases.values()) and
      firmware_cases['short-image.apj']['actual_decompressed_bytes'] == 4 and
      firmware_cases['short-image.apj']['declared'] == firmware_cases['short-image.apj']['observed']['returned_length'] == 8 and
      firmware_cases['short-image.apj']['observed']['returned_hex'] == '4142434400000000' and
      firmware_cases['exact-3.apj']['observed']['returned_length'] == 8 and
      firmware_cases['exact-7.apj']['observed']['returned_length'] == 12 and
      'RESULT|short-image.apj|OK|9999|8|8|4142434400000000' in firmware_log,
      'Five synthetic files; parser only, no bootloader exchange or physical flashing.')
firmware_invalid = root / 'sitl-evidence/firmware-parser-invalid'
invalid_manifest = json.loads((firmware_invalid / 'fixtures.json').read_text())
invalid_log = (firmware_invalid / 'probe.log').read_text(errors='replace')
def independently_valid_zlib(path):
    try:
        payload = json.loads(path.read_text())
        zlib.decompress(base64.b64decode(payload['image'], validate=True))
        return True
    except (ValueError, binascii.Error, zlib.error):
        return False
check('synthetic malformed firmware parser observations',
      (firmware_invalid / 'exit.txt').read_text().strip() == '0' and len(invalid_manifest) == 4 and
      all(hashlib.sha256((firmware_invalid / row['file']).read_bytes()).hexdigest() == row['sha256']
          for row in invalid_manifest) and
      all(value in invalid_log for value in ('RESULT|invalid-base64.apj|ERROR|System.FormatException',
          'RESULT|invalid-zlib.apj|OK|9999|4|4|00000000',
          'RESULT|truncated-zlib.apj|OK|9999|4|4|41000000',
          'RESULT|zero-size.apj|OK|9999|0|-1|null', 'Possible bad file - usually safe to ignore')) and
      sum(row['independent']['status'] == 'error' for row in invalid_manifest) == 3 and
      all(independently_valid_zlib(firmware_invalid / row['file']) == (row['independent']['status'] == 'ok')
          for row in invalid_manifest),
      'Four synthetic parser inputs; no uploader, board checks, or physical flashing.')
mock_fw_dir = root / 'sitl-evidence/mock-uploader-probe-2'
mock_fw = json.loads((mock_fw_dir / 'verification.json').read_text())
mock_log = (mock_fw_dir / 'probe.log').read_text(errors='replace')
mock_cases = {item['file']: item for item in mock_fw['checks']}
check('in-memory firmware uploader guards and payload', mock_fw['passed'] and
      (mock_fw_dir / 'exit.txt').read_text().strip() == '0' and len(mock_cases) == 2 and
      all(item['passed'] and hashlib.sha256((mock_fw_dir / item['file']).read_bytes()).hexdigest() == item['input_sha256'] and
          hashlib.sha256((mock_fw_dir / (item['file'] + '.programmed.bin')).read_bytes()).hexdigest() == item['programmed_sha256']
          for item in mock_cases.values()) and
      mock_cases['short.apj']['decompressed_length'] == 248 and mock_cases['short.apj']['programmed_length'] == 252 and
      (mock_fw_dir / 'short.apj.programmed.bin').read_bytes() == b'A' * 248 + bytes(4) and
      'RESULT|short.apj|matching|OK|writes=9|erased=True|rebooted=True|bytes=252|' in mock_log and
      'RESULT|short.apj|mismatch|Exception:Firmware not suitable for this board fw:9999 - board:10000|writes=0|erased=False' in mock_log and
      'RESULT|short.apj|too-small|Exception:Firmware image is too large for this board|writes=0|erased=False' in mock_log,
      'Manual board fields and echoing in-memory fake; no physical port, detection, or bootloader.')
mock_invalid_dir = root / 'sitl-evidence/mock-uploader-invalid'
mock_invalid_input = mock_invalid_dir / 'invalid.apj'
mock_invalid_json = json.loads(mock_invalid_input.read_text())
mock_invalid_log = (mock_invalid_dir / 'probe.log').read_text(errors='replace')
check('in-memory uploader invalid compressed image',
      (mock_invalid_dir / 'exit.txt').read_text().strip() == '0' and
      mock_invalid_json['board_id'] == 9999 and mock_invalid_json['image_size'] == 252 and
      not independently_valid_zlib(mock_invalid_input) and
      (mock_invalid_dir / 'invalid.apj.programmed.bin').read_bytes() == bytes(252) and
      all(value in mock_invalid_log for value in ('Possible bad file - usually safe to ignore',
          'RESULT|invalid.apj|matching|OK|writes=9|erased=True|rebooted=True|bytes=252|tail=0000000000000000',
          'RESULT|invalid.apj|mismatch|Exception:Firmware not suitable',
          'RESULT|invalid.apj|too-small|Exception:Firmware image is too large')),
      'Invalid synthetic compressed data sent as zeros to in-memory fake; not a real device or full UI workflow.')
mock_fault_dir = root / 'sitl-evidence/mock-uploader-faults'
mock_fault_log = (mock_fault_dir / 'probe.log').read_text(errors='replace')
check('in-memory uploader erase and verification failures',
      (mock_fault_dir / 'exit.txt').read_text().strip() == '0' and
      hashlib.sha256((mock_fault_dir / 'complete.apj').read_bytes()).digest() ==
      hashlib.sha256((mock_fw_dir / 'complete.apj').read_bytes()).digest() and
      all(value in mock_fault_log for value in (
          'RESULT|complete.apj|erase-failure|Exception:bootloader reports OPERATION FAILED|writes=3|erased=True|rebooted=False|bytes=0',
          'RESULT|complete.apj|verify-mismatch|Exception:Verification failed|writes=8|erased=True|rebooted=False|bytes=252',
          'RESULT|complete.apj|matching|OK|writes=9|erased=True|rebooted=True|bytes=252')),
      'In-memory fake replies only; erased flag means command received, not physical erase.')
mock_crc_dir = root / 'sitl-evidence/mock-uploader-crc'
mock_crc_log = (mock_crc_dir / 'probe.log').read_text(errors='replace')
mock_crc_expected = 0
for crc_byte in b'A' * 252 + b'\xff' * 260:
    mock_crc_expected ^= crc_byte
    for _ in range(8):
        mock_crc_expected = (mock_crc_expected >> 1) ^ (0xedb88320 if mock_crc_expected & 1 else 0)
check('in-memory uploader CRC match and mismatch',
      (mock_crc_dir / 'exit.txt').read_text().strip() == '0' and
      mock_crc_expected == 1345416242 and
      hashlib.sha256((mock_crc_dir / 'complete.apj').read_bytes()).digest() ==
      hashlib.sha256((mock_fw_dir / 'complete.apj').read_bytes()).digest() and
      all(value in mock_crc_log for value in (
          'Expected 0x326C3150 1345416242', 'Got      0x336C3150 1345416243',
          'RESULT|complete.apj|crc-mismatch|Exception:Program CRC failed|writes=7|erased=True|rebooted=False|bytes=252',
          'Got      0x326C3150 1345416242',
          'RESULT|complete.apj|crc-matching|OK|writes=8|erased=True|rebooted=True|bytes=252')),
      'Revision-3 CRC responses from in-memory fake; no physical flash verification.')
plugin_run = root / 'sitl-evidence/plugin-loader-probe'
plugin_events = (plugin_run / 'events.txt').read_text().splitlines()
plugin_log = (plugin_run / 'probe.log').read_text(errors='replace')
check('synthetic plugin loader lifecycle decisions',
      (plugin_run / 'exit.txt').read_text().strip() == '0' and
      hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.exe').read_bytes()).digest() ==
      hashlib.sha256(exe.read_bytes()).digest() and
      hashlib.sha256((plugin_run / 'fixtures/SyntheticLifecycle.dll').read_bytes()).digest() ==
      hashlib.sha256((plugin_run / 'fixtures/DisabledLifecycle.dll').read_bytes()).digest() and
      plugin_events == ['AcceptedFixture:Init', 'RejectInitFixture:Init', 'RejectLoadedFixture:Init',
                        'ThrowInitFixture:Init', 'AcceptedFixture:Loaded', 'RejectLoadedFixture:Loaded',
                        'AcceptedFixture:Exit'] and
      all(value in plugin_log for value in ('DISABLED_EVENTS=0', 'PENDING=AcceptedFixture,RejectLoadedFixture',
          'ACTIVE=AcceptedFixture', 'PENDING_AFTER=0', 'synthetic init failure')),
      'Synthetic DLLs and direct registration/Exit calls; not scanner, scheduler or application shutdown.')
log = (root / 'sitl-evidence/missionplanner-probe/windows-probe-roundtrip.log').read_text(errors='replace')
check('SITL Mission Planner library roundtrip', all(x in log for x in (
      'OPEN=True', 'UPLOAD_RESULTS=MAV_MISSION_ACCEPTED,MAV_MISSION_ACCEPTED',
      'ROUNDTRIP_COUNT=2', 'RETURNED=-35.363,149.1655,20')),
      'Specific 4.7.2 simulator test; no UI or physical aircraft.')
mission_loss_dir = root / 'sitl-evidence/archive-mission-request-loss'
mission_loss_log = (mission_loss_dir / 'library.log').read_text(errors='replace')
mission_loss_proxy = json.loads((mission_loss_dir / 'proxy-result.json').read_text())
mission_loss_streams = json.loads((mission_loss_dir / 'stream-verification.json').read_text())
check('SITL mission request loss recovery',
      (mission_loss_dir / 'library-exit.txt').read_text().strip() == '0' and mission_loss_proxy['passed'] and
      not mission_loss_proxy['errors'] and mission_loss_streams['passed'] and
      mission_loss_streams['dropped_request']['seq'] == 0 and
      mission_loss_streams['uplink_counts']['MISSION_COUNT'] == 1 and
      any(item['seq'] == 0 for item in mission_loss_streams['forwarded_requests']) and
      {0, 1}.issubset({item['seq'] for item in mission_loss_streams['uploaded_items']}) and
      0 in mission_loss_streams['forwarded_ack_types'] and
      all(value in mission_loss_log for value in ('UPLOAD_RESULTS=MAV_MISSION_ACCEPTED,MAV_MISSION_ACCEPTED',
          'ROUNDTRIP_COUNT=2', 'RETURNED=-35.363,149.1655,20')) and
      all(hashlib.sha256((mission_loss_dir / filename).read_bytes()).hexdigest() == mission_loss_streams[key]
          for filename, key in (('to_client_input.bin', 'input_sha256'), ('to_client_output.bin', 'output_sha256'),
                                ('to_sitl_input.bin', 'uplink_sha256'), ('to_sitl_output.bin', 'uplink_sha256'),
                                ('dropped.bin', 'dropped_sha256'))),
      'One dropped request followed by a later simulator request; no claim about repeated loss.')
mission_ack_dir = root / 'sitl-evidence/archive-mission-ack-loss'
mission_ack_log = (mission_ack_dir / 'library.log').read_text(errors='replace')
mission_ack_proxy = json.loads((mission_ack_dir / 'proxy-result.json').read_text())
mission_ack_streams = json.loads((mission_ack_dir / 'stream-verification.json').read_text())
check('SITL lost mission acknowledgment error with readback',
      (mission_ack_dir / 'library-exit.txt').read_text().strip() == '3' and mission_ack_proxy['passed'] and
      not mission_ack_proxy['errors'] and mission_ack_streams['passed'] and
      mission_ack_streams['dropped_request'] == {'type': 'MISSION_ACK', 'ack_type': 0} and
      sum(item['seq'] == 1 for item in mission_ack_streams['uploaded_items']) >= 2 and
      1 in mission_ack_streams['forwarded_ack_types'] and
      any(item['seq'] == 1 and item['z'] == 20 for item in mission_ack_streams['readback_items']) and
      all(value in mission_ack_log for value in ('UPLOAD_RESULTS=MAV_MISSION_ACCEPTED,MAV_MISSION_ERROR',
          'ROUNDTRIP_COUNT=2', 'RETURNED=-35.363,149.1655,20')) and
      all(hashlib.sha256((mission_ack_dir / filename).read_bytes()).hexdigest() == mission_ack_streams[key]
          for filename, key in (('to_client_input.bin', 'input_sha256'), ('to_client_output.bin', 'output_sha256'),
                                ('to_sitl_input.bin', 'uplink_sha256'), ('to_sitl_output.bin', 'uplink_sha256'),
                                ('dropped.bin', 'dropped_sha256'))),
      'Expected harness failure after one lost accepted ACK; same library readback showed waypoint persisted.')
param = (root / 'sitl-evidence/parameter-probe/library-parameter-test-2.log').read_text(errors='replace')
check('SITL parameter restore', all(x in param for x in
      ('PARAM_BEFORE=0', 'PARAM_SET_OK=True', 'PARAM_READBACK=1', 'PARAM_RESTORE_OK=True', 'PARAM_AFTER=0')),
      'One parameter; not bulk synchronization or calibration.')
ui_param_run = root / 'sitl-evidence/integrated-ui-params-write'
ui_param_log = (ui_param_run / 'application-stdout.log').read_text(errors='replace')
ui_param_result = (ui_param_run / 'application-result.txt').read_text(errors='replace')
ui_param_write_read = json.loads((ui_param_run / 'independent-readback.json').read_text())
ui_param_restore_read = json.loads((ui_param_run / 'independent-restored.json').read_text())
ui_param_relay = json.loads((ui_param_run / 'relay-result.json').read_text())
check('isolated app UI parameter write and independent readback',
      all(value in ui_param_result for value in ('open=True', 'params_received=1431', 'params_reported=1431',
          'initial_value=0.0', 'readback=1.0', 'restore_ok=True', 'restored_value=0.0')) and
      all(value in ui_param_log for value in ('Queue change LOG_DISARMED = 1',
          "setParam 'LOG_DISARMED' = '1'", 'setParam gotback LOG_DISARMED : 1',
          "setParam 'LOG_DISARMED' = '0'", 'setParam gotback LOG_DISARMED : 0')) and
      ui_param_write_read['passed'] and ui_param_write_read['value'] == 1 and
      ui_param_restore_read['passed'] and ui_param_restore_read['value'] == 0 and
      not ui_param_write_read['errors'] and not ui_param_restore_read['errors'] and
      not ui_param_relay['errors'] and ui_param_relay['from_app_bytes'] > 0 and ui_param_relay['to_app_bytes'] > 0 and
      (ui_param_run / 'exit.txt').read_text().strip() == '0',
      'Modified app and local relay; independent reads on secondary SITL endpoint. UI observation was not screenshot-saved.')
parameter_list = (root / 'sitl-evidence/param-list-probe/library-list.log').read_text(errors='replace')
check('SITL full parameter list', all(x in parameter_list for x in
      ('PARAM_LIST_RECEIVED=1431', 'PARAM_LIST_REPORTED=1431', 'indexseen count 1431')),
      'Regular MAVLink parameter protocol in one uninterrupted 4.8.0-dev simulator run; no GUI or FTP.')
ftp_log = (root / 'sitl-evidence/param-ftp-probe/library-list.log').read_text(errors='replace')
check('SITL FTP parameter list', all(x in ftp_log for x in
      ('GetFile 1-1 @PARAM/param.pck?withdefaults=1', 'MissionPlanner.ArduPilot.parampck',
       'PARAM_LIST_RECEIVED=1431', 'PARAM_LIST_REPORTED=1431')),
      'FTP-aware library path in one uninterrupted 4.8.0-dev simulator run; no injected loss in this run.')
ftp_drop_dir = root / 'sitl-evidence/archive-param-ftp-drop-2'
ftp_drop_log = (ftp_drop_dir / 'library.log').read_text(errors='replace')
ftp_drop_proxy = json.loads((ftp_drop_dir / 'proxy-result.json').read_text())
ftp_drop_streams = json.loads((ftp_drop_dir / 'stream-verification.json').read_text())
check('SITL FTP reply loss and regular parameter fallback',
      (ftp_drop_dir / 'library-exit.txt').read_text().strip() == '0' and ftp_drop_proxy['passed'] and
      not ftp_drop_proxy['errors'] and ftp_drop_proxy['ftp_replies_dropped'] == 10 and
      ftp_drop_streams['passed'] and not ftp_drop_streams['errors'] and
      ftp_drop_streams['dropped_valid_ftp_frames'] == 10 and
      ftp_drop_streams['uplink_message_counts']['FILE_TRANSFER_PROTOCOL'] == 10 and
      ftp_drop_streams['uplink_message_counts']['PARAM_REQUEST_LIST'] >= 1 and
      all(value in ftp_drop_log for value in ('GetFile 1-1 @PARAM/param.pck?withdefaults=1',
          'indexseen count 1431', 'PARAM_LIST_RECEIVED=1431', 'PARAM_LIST_REPORTED=1431')) and
      all(hashlib.sha256((ftp_drop_dir / filename).read_bytes()).hexdigest() == ftp_drop_streams[key]
          for filename, key in (('to_client_input.bin', 'downlink_input_sha256'),
                                ('to_client_output.bin', 'downlink_output_sha256'),
                                ('to_sitl_input.bin', 'uplink_input_sha256'),
                                ('to_sitl_output.bin', 'uplink_output_sha256'))),
      'One complete FTP-reply loss scenario; capture comparison and regular-protocol request, no GUI.')
index_loss_dir = root / 'sitl-evidence/archive-param-index-loss'
index_loss_log = (index_loss_dir / 'library.log').read_text(errors='replace')
index_loss_proxy = json.loads((index_loss_dir / 'proxy-result.json').read_text())
index_loss_streams = json.loads((index_loss_dir / 'stream-verification.json').read_text())
check('SITL dropped parameter index recovery',
      (index_loss_dir / 'library-exit.txt').read_text().strip() == '0' and index_loss_proxy['passed'] and
      not index_loss_proxy['errors'] and index_loss_streams['passed'] and not index_loss_streams['errors'] and
      sorted(index_loss_streams['dropped_indexes']) == list(range(20, 30)) and
      set(index_loss_streams['dropped_indexes']).issubset(index_loss_streams['requested_indexes']) and
      set(map(int, index_loss_streams['forwarded_recovered_indexes'])) == set(range(20, 30)) and
      index_loss_streams['uplink_counts']['PARAM_REQUEST_READ'] == 10 and
      all(value in index_loss_log for value in ('indexseen count 1431', 'PARAM_LIST_RECEIVED=1431', 'PARAM_LIST_REPORTED=1431')) and
      all(hashlib.sha256((index_loss_dir / filename).read_bytes()).hexdigest() == index_loss_streams[key]
          for filename, key in (('to_client_input.bin', 'downlink_input_sha256'),
                                ('to_client_output.bin', 'downlink_output_sha256'),
                                ('to_sitl_input.bin', 'uplink_input_sha256'),
                                ('to_sitl_output.bin', 'uplink_output_sha256'),
                                ('dropped.bin', 'dropped_sha256'))),
      'One loss of first copies of ten indexes; does not establish behavior under repeated loss.')
bulk_dir = root / 'sitl-evidence/archive-param-bulk-loss'
bulk_log = (bulk_dir / 'library.log').read_text(errors='replace')
bulk_proxy = json.loads((bulk_dir / 'proxy-result.json').read_text())
bulk_streams = json.loads((bulk_dir / 'stream-verification.json').read_text())
check('SITL bulk parameter loss full-list retry',
      (bulk_dir / 'library-exit.txt').read_text().strip() == '0' and bulk_proxy['passed'] and
      not bulk_proxy['errors'] and bulk_streams['passed'] and not bulk_streams['errors'] and
      sorted(bulk_streams['dropped_indexes']) == list(range(500)) and
      set(map(int, bulk_streams['forwarded_recovered_indexes'])) == set(range(500)) and
      bulk_streams['uplink_counts']['PARAM_REQUEST_LIST'] == 2 and
      all(value in bulk_log for value in ('Get Param whole list retry 1 got 931 75%=1071 count 1431',
          'indexseen count 1431', 'PARAM_LIST_RECEIVED=1431', 'PARAM_LIST_REPORTED=1431')) and
      all(hashlib.sha256((bulk_dir / filename).read_bytes()).hexdigest() == bulk_streams[key]
          for filename, key in (('to_client_input.bin', 'downlink_input_sha256'),
                                ('to_client_output.bin', 'downlink_output_sha256'),
                                ('to_sitl_input.bin', 'uplink_input_sha256'),
                                ('to_sitl_output.bin', 'uplink_output_sha256'),
                                ('dropped.bin', 'dropped_sha256'))),
      'One first-copy loss pattern that triggers a full-list retry; not sustained loss.')
repeat_dir = root / 'sitl-evidence/archive-param-repeat-loss'
repeat_log = (repeat_dir / 'library.log').read_text(errors='replace')
repeat_proxy = json.loads((repeat_dir / 'proxy-result.json').read_text())
repeat_streams = json.loads((repeat_dir / 'stream-verification.json').read_text())
check('SITL repeated parameter response loss recovery',
      (repeat_dir / 'library-exit.txt').read_text().strip() == '0' and repeat_proxy['passed'] and
      not repeat_proxy['errors'] and repeat_streams['passed'] and not repeat_streams['errors'] and
      repeat_streams['dropped_indexes'] == [20, 20, 20] and
      repeat_streams['requested_indexes'].count(20) >= 3 and
      '20' in repeat_streams['forwarded_recovered_indexes'] and
      all(value in repeat_log for value in ('indexseen count 1431', 'PARAM_LIST_RECEIVED=1431', 'PARAM_LIST_REPORTED=1431')) and
      all(hashlib.sha256((repeat_dir / filename).read_bytes()).hexdigest() == repeat_streams[key]
          for filename, key in (('to_client_input.bin', 'downlink_input_sha256'),
                                ('to_client_output.bin', 'downlink_output_sha256'),
                                ('to_sitl_input.bin', 'uplink_input_sha256'),
                                ('to_sitl_output.bin', 'uplink_output_sha256'),
                                ('dropped.bin', 'dropped_sha256'))),
      'Three consecutive losses for one index followed by recovery; not indefinite loss.')
log_list = (root / 'sitl-evidence/nonempty-log-probe/library-list-2.log').read_text(errors='replace')
check('nonempty SITL log list', 'LOG_LIST_COUNT=1' in log_list and 'LOG_ENTRY=1,1183744' in log_list,
      'Source-built Copter, disarmed logging; listing is not log download or playback.')
logdir = root / 'sitl-evidence/nonempty-log-probe'
download = logdir / 'downloaded.bin'
original = logdir / 'logs/00000001.BIN'
log_result = json.loads((logdir / 'download-verification.json').read_text())
download_log = (logdir / 'download-attempt-3.log').read_text(errors='replace')
check('nonempty SITL log download', 'LOG_DOWNLOAD_BYTES=5660672' in download_log and
      log_result['byte_identical'] and log_result['message_count'] == 140847 and
      hashlib.sha256(download.read_bytes()).hexdigest() == hashlib.sha256(original.read_bytes()).hexdigest() == log_result['download_sha256'],
      'One log downloaded through the original library and parsed independently; no GUI playback.')
repro = json.loads((logdir / 'empty-unit-reproduction.json').read_text())
check('empty UNIT conversion reproduction', repro['fixture_bytes_differ'] == 1 and
      repro['results']['empty']['exit_code'] == repro['results']['nonempty']['exit_code'] == 0 and
      repro['results']['empty']['bad_line_warning'] and not repro['results']['nonempty']['bad_line_warning'] and
      len(repro['results']['empty']['lines']) == 1 and len(repro['results']['nonempty']['lines']) == 2 and
      repro['results']['nonempty']['lines'][1] == 'UNIT, 2459849, 45, x',
      'One extracted record and a one-byte synthetic control; exception is swallowed by converter.')
truncated = json.loads((logdir / 'truncated-mag-reproduction.json').read_text())
check('truncated MAG conversion reproduction', truncated['expected_record_bytes'] == 35 and
      truncated['results']['partial']['record_bytes'] == 31 and
      truncated['results']['completed']['record_bytes'] == 35 and truncated['outputs_equal'] and
      truncated['results']['partial']['exit_code'] == truncated['results']['completed']['exit_code'] == 0 and
      len(truncated['results']['partial']['lines']) == 2,
      'One captured incomplete record and a zero-completed synthetic control; not every truncated log.')
browser_run = root / 'sitl-evidence/isolated-log-browser'
browser_log = (browser_run / 'application-stdout.log').read_text(errors='replace')
gps_summary = json.loads((browser_run / 'gps-altitude-summary.json').read_text())
check('log browser graph backing evidence', all(value in browser_log for value in
      ('LogBrowse_Load Done', 'LoadLog Done', 'GraphItem: GPS Alt 0', 'Graphing GPS - Alt')) and
      gps_summary['samples'] == 391 and abs(gps_summary['minimum_m'] - 578.12) < 0.01 and
      abs(gps_summary['maximum_m'] - 584.09) < 0.01 and
      (browser_run / 'exit.txt').read_text().strip() == '0',
      'Logs and independent range only; rendered graph observation was not saved as a screenshot.')
cache_root = root / 'sitl-evidence/map-cache-probe'
cache_log = (cache_root / 'probe.log').read_text(errors='replace')
cache_file = cache_root / 'cacheTileDBv3/en/OpenStreetMap/16/23456/12345.jpg'
check('local map cache overwrite observation', all(value in cache_log for value in
      ('INSERTED=True', 'FOUND=True', 'MISSING_FOUND=False', 'FIRST_MATCH=True',
       'OVERWRITE_OK=True', 'SECOND_LENGTH=24', 'SECOND_CONTENT=xffline-cache-fixture-v1')) and
      cache_file.read_bytes() == b'xffline-cache-fixture-v1',
      'Synthetic payload in file cache with patched data path; no image decoding or network provider.')
decode_log = (root / 'sitl-evidence/map-decode-probe/probe.log').read_text(errors='replace')
check('local map cache synthetic image decode', all(value in decode_log for value in
      ('INSERTED=True', 'SIZE=2x2', 'FIRST_PIXEL=255,0,0')),
      'One synthetic PNG decoded through local cache; no map display or online provider.')
check('map test library hashes match portable', all(
      hashlib.sha256((root / 'mission-planner-isolated' / name).read_bytes()).digest() ==
      hashlib.sha256((root / 'mission-planner-portable' / name).read_bytes()).digest()
      for name in ('MissionPlanner.Maps.dll', 'GMap.NET.Core.dll', 'GMap.NET.Drawing.dll')),
      'Only these three libraries match; the test copy uses a modified utility DLL.')
mjpeg_dir = root / 'sitl-evidence/mjpeg-capture-probe'
mjpeg_server = json.loads((mjpeg_dir / 'server-result.json').read_text())
mjpeg_log = (mjpeg_dir / 'capture.log').read_text(errors='replace')
check('localhost synthetic MJPEG capture', mjpeg_server['passed'] and not mjpeg_server['errors'] and
      mjpeg_server['requests'] == 1 and mjpeg_server['frames_sent'] == 3 and
      (mjpeg_dir / 'capture-exit.txt').read_text().strip() == '0' and
      all(hashlib.sha256((mjpeg_dir / item['file']).read_bytes()).hexdigest() == item['sha256']
          for item in mjpeg_server['fixture_sha256']) and
      all(value in mjpeg_log for value in ('FRAME=1 SIZE=16x16 RGB=254,0,0',
          'FRAME=2 SIZE=16x16 RGB=0,255,1', 'FRAME=3 SIZE=16x16 RGB=0,0,254',
          'CLEAR_EVENT=True', 'FRAMES=3', 'STOP_CLEAR=True')),
      'Synthetic local stream and direct library callback; no HUD, GStreamer or camera.')
mjpeg_error_dir = root / 'sitl-evidence/mjpeg-missing-length'
mjpeg_error_server = json.loads((mjpeg_error_dir / 'server-result.json').read_text())
mjpeg_error_log = (mjpeg_error_dir / 'capture.log').read_text(errors='replace')
check('MJPEG missing length reconnect', mjpeg_error_server['passed'] and not mjpeg_error_server['errors'] and
      mjpeg_error_server['requests'] == 2 and mjpeg_error_server['frames_sent'] == 4 and
      (mjpeg_error_dir / 'capture-exit.txt').read_text().strip() == '0' and
      all(hashlib.sha256((mjpeg_error_dir / item['file']).read_bytes()).hexdigest() == item['sha256']
          for item in mjpeg_error_server['fixture_sha256']) and
      'KeyNotFoundException' in mjpeg_error_log and mjpeg_error_log.count('CLEAR_EVENT=True') == 2 and
      all(value in mjpeg_error_log for value in ('FRAME=1 SIZE=16x16 RGB=254,0,0',
          'FRAME=2 SIZE=16x16 RGB=0,255,1', 'FRAME=3 SIZE=16x16 RGB=0,0,254',
          'CLEAR_BEFORE_FRAME=True', 'STOP_CLEAR=True')),
      'One missing Content-Length followed by a valid local stream; no HUD or camera.')
hud_video = root / 'sitl-evidence/mjpeg-hud-ui-2'
hud_video_server = json.loads((hud_video / 'server-result.json').read_text())
hud_video_result = (hud_video / 'application-result.txt').read_text(errors='replace')
check('modified app MJPEG HUD backing evidence', hud_video_server['passed'] and not hud_video_server['errors'] and
      hud_video_server['requests'] == 1 and hud_video_server['frames_sent'] >= 1 and
      hashlib.sha256((hud_video / 'synthetic-hud.jpg').read_bytes()).hexdigest() == hud_video_server['fixture_sha256'] and
      all(value in hud_video_result for value in ('hud_image=640x480', 'image_found=True',
                                                   'stop_called=True', 'hud_cleared=True')) and
      (hud_video / 'exit.txt').read_text().strip() == '1',
      'Patched app and synthetic localhost stream; visual HUD observation not screenshot-saved; process forcibly terminated.')
truncated_runs = [root / 'sitl-evidence/mjpeg-truncated-body', root / 'sitl-evidence/mjpeg-truncated-body-2',
                  root / 'sitl-evidence/mjpeg-truncated-body-3']
truncated_logs = [(path / 'capture.log').read_text(errors='replace') for path in truncated_runs]
truncated_servers = [json.loads((path / 'server-result.json').read_text()) for path in truncated_runs]
cpu_match = re.search(r'CPU_MS_DURING_STOP_WAIT=([0-9.]+)', truncated_logs[1])
check('MJPEG truncated-body worker after stop',
      all(server['passed'] and not server['errors'] and server['scenario'] == 'truncated_body' and
          server['requests'] == 1 and server['frames_sent'] == 1 for server in truncated_servers) and
      all((path / 'capture-exit.txt').read_text().strip() == '0' for path in truncated_runs) and
      all(all(value in log for value in ('Content-Length: 685', 'FRAMES=0', 'CLEAR_EVENTS=0',
                                         'WORKER_ALIVE_AFTER_STOP=True')) for log in truncated_logs) and
      cpu_match is not None and float(cpu_match.group(1)) > 500 and
      'RESTART_RETURNED_WITHIN_1S=False' in truncated_logs[2] and
      all(hashlib.sha256((path / item['file']).read_bytes()).hexdigest() == item['sha256']
          for path, server in zip(truncated_runs, truncated_servers) for item in server['fixture_sha256']),
      'Three bounded synthetic EOF tests; CPU is process-wide and no worker stack was captured.')
offline = root / 'sitl-evidence/offline-map-ui'
tile_manifest = json.loads((offline / 'tile-manifest.json').read_text())
tile_root = root / 'mission-planner-runtime/isolated-data/gmapcache/TileDBv3/en/OpenStreetMap/3'
expected_tiles = {f'{y}/{x}.jpg' for y in range(8) for x in range(8)}
check('offline map UI fixture integrity', tile_manifest['count'] == len(tile_manifest['files']) == 64 and
      {item['path'] for item in tile_manifest['files']} == expected_tiles and
      all(hashlib.sha256((tile_root / item['path']).read_bytes()).hexdigest() == item['sha256']
          for item in tile_manifest['files']) and
      'SEEDED=64' in (offline / 'seed.log').read_text() and
      'applied=True' in (offline / 'application-result.txt').read_text() and
      (offline / 'exit.txt').read_text().strip() == '0',
      'Synthetic fixtures and app status only; visual observation was not saved as a screenshot.')
built = root / 'sitl-evidence/archive-built/arducopter'
built_sha = hashlib.sha256(built.read_bytes()).hexdigest()
alt_fence = json.loads((root / 'sitl-evidence/archive-copter-alt-fence/results.json').read_text())
fence_checks = alt_fence['checks']
check('source-built Copter maximum-altitude fence response', alt_fence['passed'] and not alt_fence['errors'] and
      alt_fence['binary_sha256'] == built_sha and all(item['passed'] for item in fence_checks.values()) and
      fence_checks['configuration']['values'] == {'FENCE_ENABLE': 0, 'FENCE_TYPE': 1, 'FENCE_ALT_MAX': 10, 'FENCE_ACTION': 2} and
      fence_checks['above_limit_before_enable']['relative_alt_m'] >= 11.5 and
      fence_checks['fence_enabled']['value'] == 1 and fence_checks['fence_land_mode']['mode'] == 9 and
      'Max Alt fence breached' in alt_fence['status_messages'] and 'Fence breach cleared' in alt_fence['status_messages'],
      'One already-breached altitude fence enabled in disposable SITL; no physical aircraft or other fence types.')
lua_run = root / 'sitl-evidence/archive-lua-scripting-retry'
lua_result = json.loads((lua_run / 'results.json').read_text())
check('SITL Lua scheduled messages', lua_result['passed'] and not lua_result['errors'] and
      lua_result['binary_sha256'] == built_sha and lua_result['scr_enable'] == 1 and
      hashlib.sha256((lua_run / 'scripts/codex_probe.lua').read_bytes()).hexdigest() == lua_result['script_sha256'] and
      lua_result['messages'] == ['CODEX_LUA_PROBE 1', 'CODEX_LUA_PROBE 2', 'CODEX_LUA_PROBE 3'],
      'One benign script in disposable Copter SITL; no failure or security testing.')
lua_limit_dir = root / 'sitl-evidence/archive-lua-instruction-limit'
lua_limit = json.loads((lua_limit_dir / 'results.json').read_text())
limit_text = lua_limit['status_text']
limit_error = next((i for i, value in enumerate(limit_text) if 'codex_limit.lua exceeded time limit' in value), None)
check('SITL Lua instruction limit', lua_limit['passed'] and not lua_limit['errors'] and
      lua_limit['binary_sha256'] == built_sha and lua_limit['scr_enable'] == 1 and
      hashlib.sha256((lua_limit_dir / 'scripts/codex_limit.lua').read_bytes()).hexdigest() == lua_limit['limit_script_sha256'] and
      limit_error is not None and any('CODEX_LUA_PROBE ' in value for value in limit_text[limit_error + 1:]),
      'One deliberate instruction-limit event and later message from another script; no security assessment.')
lua_disabled_dir = root / 'sitl-evidence/archive-lua-disabled-directory'
lua_disabled = json.loads((lua_disabled_dir / 'results.json').read_text())
check('SITL Lua disabled script directory', lua_disabled['passed'] and not lua_disabled['errors'] and
      lua_disabled['binary_sha256'] == built_sha and lua_disabled['scr_enable'] == 1 and
      lua_disabled['scr_dir_disable'] == 2 and lua_disabled['observation_seconds'] >= 15 and
      not lua_disabled['messages'] and any('All directory' in value and 'SCR_DIR_DISABLE' in value for value in lua_disabled['status_text']) and
      hashlib.sha256((lua_disabled_dir / 'scripts/codex_probe.lua').read_bytes()).hexdigest() == lua_disabled['script_sha256'] == lua_result['script_sha256'],
      'One 15-second observation with the same script fixture and disabled directory; not every script source.')
blimp = root / 'sitl-evidence/archive-built-variants/blimp'
blimp_result = json.loads((root / 'sitl-evidence/archive-blimp-smoke/results.json').read_text())
extra_status = json.loads((root / 'sitl-evidence/archive-linux-extras-retry2-build-status.json').read_text())
blimp_publish = next(x for x in extra_status['steps'] if x['step'] == 'publish blimp binary')
check('source-built Blimp SITL smoke', blimp_result['passed'] and not blimp_result['errors'] and
      all(x['passed'] for x in blimp_result['checks'].values()) and
      hashlib.sha256(blimp.read_bytes()).hexdigest() == blimp_result['binary_sha256'] == blimp_publish['sha256'] and
      blimp_publish['status'] == 'complete',
      'Locally built Blimp SITL; basic telemetry, parameter and mission count only.')
tracker = root / 'sitl-evidence/archive-built-variants/antennatracker'
tracker_result = json.loads((root / 'sitl-evidence/archive-antennatracker-smoke/results.json').read_text())
tracker_publish = next(x for x in extra_status['steps'] if x['step'] == 'publish antennatracker binary')
check('source-built AntennaTracker SITL smoke', tracker_result['passed'] and not tracker_result['errors'] and
      all(x['passed'] for x in tracker_result['checks'].values()) and
      tracker_result['checks']['parameter_read']['name'] == 'YAW_SLEW_TIME' and
      hashlib.sha256(tracker.read_bytes()).hexdigest() == tracker_result['binary_sha256'] == tracker_publish['sha256'] and
      tracker_publish['status'] == 'complete',
      'Locally built tracker SITL; basic telemetry, parameter and mission count, not target tracking.')
variant_folder = root / 'sitl-evidence/archive-built-variants'
variant_rea = json.loads((variant_folder / 'rea-variant-manifest.json').read_text())
check('source-built variant REA artifact inventories', len(variant_rea) == 10 and
      {(x['binary'], x['operation']) for x in variant_rea} ==
      {(name, operation) for name in ('arduplane', 'ardurover', 'ardusub', 'blimp', 'antennatracker')
       for operation in ('inspect-elf-notes', 'inspect-native-exports')} and
      all(x['exit_code'] == 0 and x['digest_matches'] and x['coverage'] == 'complete' and
          hashlib.sha256((variant_folder / x['binary']).read_bytes()).hexdigest() == x['sha256'] and
          json.loads((variant_folder / x['output']).read_text())['subject']['digest']['sha256'] == x['sha256']
          for x in variant_rea),
      'ELF notes and native exports only; not full native behavior or disassembly.')
fence_rally = json.loads((root / 'sitl-evidence/archive-fence-rally-rejection/results.json').read_text())
fr = fence_rally['checks']
check('fence and rally rejected replacement readback', fence_rally['passed'] and
      fence_rally['binary_sha256'] == built_sha and not fence_rally['errors'] and
      all(v['passed'] for v in fr.values()) and
      fr['fence_rejection']['upload']['ack_name'] == fr['rally_rejection']['upload']['ack_name'] == 'MAV_MISSION_UNSUPPORTED_FRAME' and
      fr['fence_rejection']['readback'] == fr['fence_baseline']['readback'] and
      fr['rally_rejection']['readback'][0]['lat'] == fr['rally_baseline']['readback'][0]['lat'] + 5000 and
      fr['rally_rejection']['readback'][1] == fr['rally_baseline']['readback'][1],
      'One rejected replacement per type, standalone client and disposable Copter SITL; not general atomicity.')
build_status = json.loads((root / 'sitl-evidence/archive-linux-build-status.json').read_text())
published = next(x for x in build_status['steps'] if x['step'] == 'publish local SITL binary')
check('exact-source SITL binary provenance', build_status['status'] == 'complete' and
      build_status['commit'] == prov['candidate_commit_from_zip_comment'] and
      published['status'] == 'complete' and published['sha256'] == built_sha,
      'Local SITL build from extracted pinned files, not an official release binary.')
for folder in ('archive-copter-smoke', 'archive-copter-mission'):
    result = json.loads((root / 'sitl-evidence' / folder / 'results.json').read_text())
    check(folder, result['passed'] and result['binary_sha256'] == built_sha and
          all(v['passed'] for v in result['checks'].values()),
          'Specific test-client checks; no physical aircraft.')
invalid_mission = json.loads((root / 'sitl-evidence/archive-mission-invalid-frame/results.json').read_text())
invalid_readback = invalid_mission['post_rejection_readback']
check('exact-source invalid mission frame', invalid_mission['binary_sha256'] == built_sha and
      invalid_mission['passed'] and invalid_mission['checks']['invalid_rejected']['upload']['ack_name'] == 'MAV_MISSION_UNSUPPORTED_FRAME' and
      invalid_readback.get('count') == 2 and invalid_readback.get('lat_e7') == -353630000 and
      invalid_readback.get('lon_e7') == 1491655000 and abs(invalid_readback.get('alt_m', 0) - 20) < 0.01,
      'One unsupported-frame case; not general transaction atomicity or application UI behavior.')
partial_mission = json.loads((root / 'sitl-evidence/archive-mission-partial-write/results.json').read_text())
check('exact-source rejected mission partial update', partial_mission['binary_sha256'] == built_sha and
      partial_mission['passed'] and partial_mission['checks']['baseline']['readback']['alt_m'] == 20.0 and
      partial_mission['checks']['invalid_rejected']['upload']['ack_name'] == 'MAV_MISSION_UNSUPPORTED_FRAME' and
      partial_mission['post_rejection_readback'].get('count') == 3 and
      partial_mission['post_rejection_readback'].get('alt_m') == 25.0,
      'One failed upload left an earlier item changed; not a claim about all failures or firmware versions.')
short_mission = json.loads((root / 'sitl-evidence/archive-mission-rejected-truncation/results.json').read_text())
check('exact-source rejected mission truncation', short_mission['binary_sha256'] == built_sha and
      short_mission['passed'] and short_mission['checks']['baseline']['readback']['count'] == 4 and
      short_mission['checks']['invalid_rejected']['upload']['ack_name'] == 'MAV_MISSION_UNSUPPORTED_FRAME' and
      short_mission['post_rejection_readback'].get('count') == 3 and
      short_mission['post_rejection_readback'].get('alt_m') == 25.0,
      'One rejected shorter upload reduced mission count and retained a prior changed item; no generality implied.')
flight = json.loads((root / 'sitl-evidence/archive-copter-flight-3/results.json').read_text())
check('exact-source Copter simulated flight', flight['binary_sha256'] == built_sha and flight['passed'] and
      set(flight['checks']) == {'guided_mode', 'armed', 'takeoff', 'land_mode', 'landed_and_disarmed'} and
      all(value['passed'] for value in flight['checks'].values()) and
      flight['checks']['takeoff']['peak_relative_alt_m'] >= 3.0,
      'One simulated flight with standalone client; touchdown location and physical aircraft not tested.')
gps_dir = root / 'sitl-evidence/archive-copter-gps-loss'
gps_result_file = gps_dir / 'results.json'
gps_result = json.loads(gps_result_file.read_text())
gps_summary = json.loads((gps_dir / 'transition-summary.json').read_text())
gps_events = gps_result['events']
gps_disable = next(event['seconds'] for event in gps_events if event['type'] == 'gps_disable_confirmed')
gps_restore = next(event['seconds'] for event in gps_events if event['type'] == 'gps_restore_confirmed')
gps_loss = next(event['seconds'] for event in gps_events if event['type'] == 'GPS_RAW_INT' and
                event['fix_type'] < 3 and gps_disable < event['seconds'] < gps_restore)
gps_land = next(event['seconds'] for event in gps_events if event['type'] == 'HEARTBEAT' and
                event['mode'] == 9 and event['armed'] and gps_disable < event['seconds'] < gps_restore)
gps_disarm_notice = next(event['seconds'] for event in gps_events if event['type'] == 'STATUSTEXT' and
                         event['text'] == 'Disarming motors' and gps_disable < event['seconds'] < gps_restore)
gps_recovery = next(event['seconds'] for event in gps_events if event['type'] == 'GPS_RAW_INT' and
                    event['fix_type'] >= 3 and event['seconds'] > gps_restore)
check('exact-source Copter simulated GPS outage', gps_result['passed'] and not gps_result['errors'] and
      gps_result['binary_sha256'] == built_sha and all(value['passed'] for value in gps_result['checks'].values()) and
      hashlib.sha256(gps_result_file.read_bytes()).hexdigest() == gps_summary['source_sha256'] and
      gps_disable < gps_loss < gps_land < gps_disarm_notice < gps_restore < gps_recovery and
      'EKF variance: position lost' in gps_result['status_messages'] and
      'EKF Failsafe: changed to Land Mode' in gps_result['status_messages'] and
      'EKF Failsafe Cleared' in gps_result['status_messages'],
      'One simulated GPS outage; GPS was restored after disarm notice, with no physical-flight or in-flight recovery claim.')
short_dir = root / 'sitl-evidence/archive-copter-gps-short-loss'
short_file = short_dir / 'results.json'
short = json.loads(short_file.read_text())
short_summary = json.loads((short_dir / 'transition-summary.json').read_text())
short_events = short['events']
short_disable = next(event['seconds'] for event in short_events if event['type'] == 'gps_disable_confirmed')
short_restore = next(event['seconds'] for event in short_events if event['type'] == 'gps_restore_confirmed')
short_loss = next(event['seconds'] for event in short_events if event['type'] == 'GPS_RAW_INT' and
                  event['fix_type'] < 3 and short_disable < event['seconds'] < short_restore)
short_fix = next(event['seconds'] for event in short_events if event['type'] == 'GPS_RAW_INT' and
                 event['fix_type'] >= 3 and event['seconds'] > short_restore)
short_guided = next(event['seconds'] for event in short_events if event['type'] == 'HEARTBEAT' and
                    event['mode'] == 4 and event['armed'] and event['seconds'] > short_fix)
short_land = next(event['seconds'] for event in short_events if event['type'] == 'HEARTBEAT' and
                  event['mode'] == 9 and event['armed'] and event['seconds'] > short_guided)
check('exact-source Copter short GPS outage recovery', short['passed'] and not short['errors'] and
      short['binary_sha256'] == built_sha and all(value['passed'] for value in short['checks'].values()) and
      hashlib.sha256(short_file.read_bytes()).hexdigest() == short_summary['source_sha256'] and
      short_disable < short_loss < short_restore < short_fix < short_guided < short_land and
      'EKF Failsafe: changed to Land Mode' not in short['status_messages'],
      'One short simulated GPS outage with recovery before commanded LAND; no physical-flight claim.')
rover = json.loads((root / 'sitl-evidence/archive-rover-gcs-failsafe-3/results.json').read_text())
rover_events = rover['events']
stop_time = next(event['seconds'] for event in rover_events if event['kind'] == 'stop_gcs_heartbeats')
hold_time = next(event['seconds'] for event in rover_events if event['kind'] == 'heartbeat' and
                 event['mode'] == 4 and not event['sending_heartbeats'] and event['seconds'] >= stop_time)
notice_time = next(event['seconds'] for event in rover_events if event['kind'] == 'status' and event['text'] == 'GCS Failsafe')
clear_time = next(event['seconds'] for event in rover_events if event['kind'] == 'status' and event['text'] == 'GCS Failsafe Cleared')
check('exact-source Rover simulated GCS failsafe', rover['passed'] and not rover['errors'] and
      rover['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built-variants/ardurover').read_bytes()).hexdigest() and
      all(value['passed'] for value in rover['checks'].values()) and
      rover['checks']['configuration']['values'] == {'FS_THR_ENABLE': 0, 'FS_GCS_ENABLE': 1,
                                                       'FS_GCS_TIMEOUT': 3, 'FS_TIMEOUT': 1, 'FS_ACTION': 2} and
      rover['checks']['gcs_loss_hold']['hold_mode'] == 4 and
      stop_time <= hold_time <= notice_time < clear_time and 'Radio Failsafe' not in rover['status_messages'],
      'One Rover SITL GCS-loss case; movement was not commanded or measured, and no physical-vehicle or timeout-accuracy claim.')
battery = json.loads((root / 'sitl-evidence/archive-copter-battery-failsafe/results.json').read_text())
check('exact-source Copter simulated battery failsafe', battery['binary_sha256'] == built_sha and battery['passed'] and
      all(value['passed'] for value in battery['checks'].values()) and
      battery['checks']['configuration']['values']['BATT_LOW_TIMER'] == 2 and
      battery['checks']['configuration']['values']['BATT_FS_LOW_ACT'] == 1 and
      battery['checks']['raise_threshold']['threshold_v'] > battery['checks']['takeoff_and_voltage']['voltage_v'] and
      battery['checks']['land_mode']['mode'] == 9 and 'Battery Failsafe' in battery['status_messages'] and
      any(text.startswith('Battery 1 is low ') for text in battery['status_messages']),
      'One threshold-raised simulated battery case; no physical discharge, exact timing, or GUI test.')
failsafe = json.loads((root / 'sitl-evidence/archive-copter-gcs-failsafe/results.json').read_text())
check('exact-source Copter simulated GCS failsafe', failsafe['binary_sha256'] == built_sha and failsafe['passed'] and
      all(value['passed'] for value in failsafe['checks'].values()) and
      'GCS Failsafe' in failsafe['status_messages'] and 'GCS Failsafe Cleared' in failsafe['status_messages'],
      'One configured GCS heartbeat-loss scenario; no physical aircraft or timeout-duration measurement.')
resume_first = json.loads((root / 'sitl-evidence/archive-copter-mission-resume/results.json').read_text())
resume_retry = json.loads((root / 'sitl-evidence/archive-copter-mission-resume-2/results.json').read_text())
resume_events = resume_retry['events']
brake_time = next(event['seconds'] for event in resume_events if event['type'] == 'BRAKE_observed' and event['observed'])
resume_time = next(event['seconds'] for event in resume_events if event['type'] == 'AUTO_resumed' and event['observed'])
after_two = next(event['seconds'] for event in resume_events if event['type'] == 'MISSION_CURRENT' and
                 event['phase'] == 'after_resume' and event['seq'] == 2)
reached_two = next(event['seconds'] for event in resume_events if event['type'] == 'MISSION_ITEM_REACHED' and event['seq'] == 2)
after_three = next(event['seconds'] for event in resume_events if event['type'] == 'MISSION_CURRENT' and
                   event['phase'] == 'after_resume' and event['seq'] == 3)
check('exact-source Copter mission pause and resume', not resume_first['passed'] and
      not resume_first['checks']['resumed_mode']['passed'] and 'Auto: Missing Takeoff Cmd' in resume_first['status_messages'] and
      resume_retry['passed'] and not resume_retry['errors'] and resume_retry['binary_sha256'] == built_sha and
      all(value['passed'] for value in resume_retry['checks'].values()) and
      resume_retry['checks']['resume_option']['value'] == 0 and resume_retry['checks']['pause_mode']['mode'] == 17 and
      all(seq == 2 for seq in resume_retry['checks']['paused_sequence']['sequences']) and
      len(resume_retry['checks']['paused_sequence']['altitude_samples_m']) > 0 and
      min(resume_retry['checks']['paused_sequence']['altitude_samples_m']) > 3 and
      brake_time < resume_time < after_two < reached_two < after_three,
      'BRAKE and MIS_RESTART=0 in one source-built simulation; initial LOITER failure retained; no UI or completion-notification claim.')
loiter_centered = json.loads((root / 'sitl-evidence/archive-copter-mission-loiter-centered/results.json').read_text())
loiter_events = loiter_centered['events']
loiter_start = next(event['seconds'] for event in loiter_events if event['type'] == 'LOITER_observed' and event['observed'])
loiter_resume = next(event['seconds'] for event in loiter_events if event['type'] == 'AUTO_resumed' and event['observed'])
loiter_reached = next(event['seconds'] for event in loiter_events if event['type'] == 'MISSION_ITEM_REACHED' and event['seq'] == 2)
loiter_altitudes = loiter_centered['checks']['paused_sequence']['altitude_samples_m']
loiter_pwm = loiter_centered['checks']['throttle_override_observed']['samples_pwm']
check('exact-source Copter centered-throttle LOITER retry', loiter_centered['passed'] and not loiter_centered['errors'] and
      loiter_centered['binary_sha256'] == built_sha and all(value['passed'] for value in loiter_centered['checks'].values()) and
      loiter_centered['checks']['pause_mode']['mode'] == 5 and loiter_centered['checks']['resume_option']['value'] == 0 and
      bool(loiter_altitudes) and min(loiter_altitudes) > 3 and bool(loiter_pwm) and
      all(value == 1500 for value in loiter_pwm) and loiter_start < loiter_resume < loiter_reached,
      'One centered RC override in SITL; the earlier LOITER descent remains unexplained and no physical radio was tested.')
post_landing = json.loads((root / 'sitl-evidence/archive-copter-mission-disarm-observe/results.json').read_text())
post_events = post_landing['events']
disarming_i = next(i for i, event in enumerate(post_events) if event['type'] == 'STATUSTEXT' and event['text'] == 'Disarming motors')
takeoff_i = next(i for i, event in enumerate(post_events) if i > disarming_i and event['type'] == 'STATUSTEXT' and event['text'] == 'Mission: 1 Takeoff')
disarmed_i = next(i for i, event in enumerate(post_events) if i > takeoff_i and event['type'] == 'HEARTBEAT' and not event['armed'])
post_hb = [event for event in post_events if event.get('phase') == 'post_disarm' and event['type'] == 'HEARTBEAT']
post_seq = [event['seq'] for event in post_events if event.get('phase') == 'post_disarm' and event['type'] == 'MISSION_CURRENT']
check('exact-source Copter post-disarm mission telemetry', post_landing['passed'] and not post_landing['errors'] and
      post_landing['binary_sha256'] == built_sha and all(value['passed'] for value in post_landing['checks'].values()) and
      disarming_i < takeoff_i < disarmed_i and post_events[disarmed_i]['mode'] == 3 and
      len(post_hb) >= 1 and all(not event['armed'] and event['mode'] == 3 for event in post_hb) and 1 in post_seq,
      'One SITL run; no post-disarm command was issued by the harness; mission internals were not instrumented.')
restart = json.loads((root / 'sitl-evidence/archive-copter-mission-restart/results.json').read_text())
restart_events = restart['events']
restart_request = next(event['seconds'] for event in restart_events if event['type'] == 'AUTO_restart_requested')
restart_takeoff = next(event['seconds'] for event in restart_events if event['type'] == 'STATUSTEXT' and
                       event['text'] == 'Mission: 1 Takeoff' and event['seconds'] >= restart_request)
restart_reached_one = next(event['seconds'] for event in restart_events if event['type'] == 'MISSION_ITEM_REACHED' and
                           event['seq'] == 1 and event['seconds'] >= restart_request)
restart_reached_two = next(event['seconds'] for event in restart_events if event['type'] == 'MISSION_ITEM_REACHED' and
                           event['seq'] == 2 and event['seconds'] >= restart_request)
check('exact-source Copter mission restart option', restart['passed'] and not restart['errors'] and
      restart['binary_sha256'] == built_sha and all(value['passed'] for value in restart['checks'].values()) and
      restart['checks']['resume_option']['value'] == 1 and restart['checks']['pause_mode']['mode'] == 17 and
      all(seq == 2 for seq in restart['checks']['paused_sequence']['sequences']) and
      restart_request <= restart_takeoff <= restart_reached_one < restart_reached_two,
      'One already-airborne MIS_RESTART=1 simulation; no general restart, GUI or completion-notification claim.')
mission_flight = json.loads((root / 'sitl-evidence/archive-copter-auto-mission/results.json').read_text())
check('exact-source Copter Auto mission', mission_flight['binary_sha256'] == built_sha and mission_flight['passed'] and
      all(value['passed'] for value in mission_flight['checks'].values()) and
      all(index in mission_flight['mission_current'] for index in (1, 2, 3)) and
      all(index in mission_flight['mission_reached'] for index in (1, 2)),
      'One standalone-client simulator mission; completion notification and GUI not verified.')
variant_status = json.loads((root / 'sitl-evidence/archive-linux-variants-build-status.json').read_text())
for variant in ('plane', 'rover', 'sub'):
    step = next(x for x in variant_status['steps'] if x['step'] == f'publish {variant} binary')
    binary = root / 'sitl-evidence/archive-built-variants' / ('ardu' + variant)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    result = json.loads((root / 'sitl-evidence' / f'archive-{variant}-smoke/results.json').read_text())
    check(f'exact-source {variant} SITL smoke', variant_status['commit'] == prov['candidate_commit_from_zip_comment'] and
          step['sha256'] == digest == result['binary_sha256'] and result['passed'] and
          all(value['passed'] for value in result['checks'].values()),
          'Local source-snapshot build, standalone client; no UI or physical aircraft.')
for variant in ('plane', 'rover', 'sub'):
    result = json.loads((root / 'sitl-evidence' / f'variant-{variant}-smoke/results.json').read_text())
    binary = root / 'sitl-evidence/variants' / variant / ('ardu' + variant)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    required = {'heartbeat', 'ATTITUDE', 'GLOBAL_POSITION_INT', 'SYS_STATUS', 'parameter_read', 'mission_list'}
    check(f'official {variant} SITL smoke', result['passed'] and result['binary_sha256'] == digest and
          required.issubset(result['checks']) and all(result['checks'][key]['passed'] for key in required),
          'Official 4.7.2 binary; standalone client, no Mission Planner UI or flight behavior.')
exact_log = (root / 'sitl-evidence/library-exact-source/windows-probe-roundtrip.log').read_text(errors='replace')
check('version-matched Mission Planner library mission', all(x in exact_log for x in (
      'OPEN=True', 'UPLOAD_RESULTS=MAV_MISSION_ACCEPTED,MAV_MISSION_ACCEPTED',
      'ROUNDTRIP_COUNT=2', 'RETURNED=-35.363,149.1655,20')),
      'Original library; no UI interaction.')
run = root / 'sitl-evidence/integrated-spool-telemetry'
lines = (run / 'application-result.txt').read_text().splitlines()
values = dict(line.split('=', 1) for line in lines if '=' in line)
relay = json.loads((run / 'relay-result.json').read_text())
check('isolated app telemetry state', values.get('open') == 'True' and values.get('system') == '1' and
      values.get('component') == '1' and abs(float(values.get('state_lat', '0')) + 35.363261) < 0.00001 and
      abs(float(values.get('state_lng', '0')) - 149.16523) < 0.00001 and
      relay['to_app_bytes'] > 0 and relay['from_app_bytes'] > 0 and not relay['errors'],
      'Data-path-patched, plugin-disabled test copy with file-spool transport; no rendered UI verification.')
ui_run = root / 'sitl-evidence/integrated-ui-telemetry'
ui_values = dict(line.split('=', 1) for line in (ui_run / 'application-result.txt').read_text().splitlines() if '=' in line)
ui_relay = json.loads((ui_run / 'relay-result.json').read_text())
check('isolated app UI telemetry backing evidence', ui_values.get('open') == 'True' and
      ui_values.get('system') == '1' and ui_values.get('component') == '1' and
      abs(float(ui_values.get('state_lat', '0')) + 35.363261) < 0.00001 and
      abs(float(ui_values.get('state_lng', '0')) - 149.16523) < 0.00001 and
      ui_relay['to_app_bytes'] > 0 and ui_relay['from_app_bytes'] > 0 and not ui_relay['errors'] and
      (ui_run / 'exit.txt').read_text().strip() == '0',
      'Verifies logs and relay only; rendered UI observation is documented separately and screenshots were not retained.')
ui_mission = root / 'sitl-evidence/integrated-ui-mission'
mission_values = (ui_mission / 'application-result.txt').read_text()
mission_log = (ui_mission / 'application-stdout.log').read_text(errors='replace')
mission_relay = json.loads((ui_mission / 'relay-result.json').read_text())
check('isolated app UI mission backing evidence', all(value in mission_values for value in
      ('open=True', 'upload_results=MAV_MISSION_ACCEPTED,MAV_MISSION_ACCEPTED', 'mission_count=2')) and
      'Getting WP0' in mission_log and 'Getting WP1' in mission_log and
      mission_relay['to_app_bytes'] > 0 and mission_relay['from_app_bytes'] > 0 and not mission_relay['errors'] and
      (ui_mission / 'exit.txt').read_text().strip() == '0',
      'Checks upload, log entries and relay; rendered row observation is separate and screenshots were not retained.')
ui_write = root / 'sitl-evidence/integrated-ui-write-2'
write_values = (ui_write / 'application-result.txt').read_text()
write_log = (ui_write / 'application-stdout.log').read_text(errors='replace')
write_relay = json.loads((ui_write / 'relay-result.json').read_text())
request = write_log.find('"z":25.0,"seq":1')
ack = write_log.find('setWPint resp MISSION_ACK', request)
readback = write_log.find('getWPint 16 0 25 -35.363 149.1655', ack)
check('isolated app UI mission write backing evidence', 'readback_alt=25.0' in write_values and
      request >= 0 and ack > request and '"type":0' in write_log[ack:ack+1200] and readback > ack and
      'Trying to set Param that doesnt exist WP_RADIUS=2' in write_log and
      write_relay['to_app_bytes'] > 0 and write_relay['from_app_bytes'] > 0 and not write_relay['errors'] and
      (ui_write / 'exit.txt').read_text().strip() == '0',
      'Logs show one UI-triggered waypoint write and later readback through custom transport; GUI observation is separate.')
ui_params = root / 'sitl-evidence/integrated-ui-params'
param_values = (ui_params / 'application-result.txt').read_text()
param_relay = json.loads((ui_params / 'relay-result.json').read_text())
check('isolated app UI parameter backing evidence', all(value in param_values for value in
      ('open=True', 'params_received=1431', 'params_reported=1431', 'initial_value=0.0', 'readback=0.0')) and
      param_relay['to_app_bytes'] > 0 and param_relay['from_app_bytes'] > 0 and not param_relay['errors'] and
      (ui_params / 'exit.txt').read_text().strip() == '0',
      'Only script and relay evidence; UI population was observed separately, no UI write was performed.')
tlog_dir = root / 'sitl-evidence/tlog-playback-probe'
tlog_fixtures = json.loads((tlog_dir / 'fixtures.json').read_text())
tlog_lines = (tlog_dir / 'probe.log').read_text(encoding='utf-16')
zero_lines = (tlog_dir / 'zero-crc-probe.log').read_text(encoding='utf-16')
fixture_integrity = all(hashlib.sha256((tlog_dir / name).read_bytes()).hexdigest() == info['sha256'] and
                        (tlog_dir / name).stat().st_size == info['size']
                        for name, info in tlog_fixtures['files'].items())
source_integrity = hashlib.sha256((root / tlog_fixtures['source']).read_bytes()).hexdigest() == tlog_fixtures['source_sha256']
zero_full = (tlog_dir / 'zero-crc-control.tlog').read_bytes()
zero_short = (tlog_dir / 'zero-crc-truncated.tlog').read_bytes()
check('telemetry-log truncation and checksum fixture', fixture_integrity and source_integrity and
      zero_full[:-1] == zero_short and zero_full[-1] == 0 and
      tlog_lines.count('VALIDATED LENGTH=0 ') == 3 and tlog_lines.count('VALIDATED LENGTH=17 ') == 1 and
      zero_lines.count('VALIDATED LENGTH=17 ') == 2 and
      'POSITION=25 FILE_LENGTH=25 HEX=FE0900FFBE00EB00000006080000035000' in zero_lines and
      'POSITION=24 FILE_LENGTH=24 HEX=FE0900FFBE00EB00000006080000035000' in zero_lines,
      'Library fixture test only: one zero-byte checksum truncation is accepted; no GUI playback claim.')
recovery_dir = root / 'sitl-evidence/tlog-recovery-probe'
recovery = json.loads((recovery_dir / 'fixtures.json').read_text())
recovery_log = (recovery_dir / 'probe.log').read_text(encoding='utf-16')
sections = {section.splitlines()[0]: section for section in recovery_log.split('FIXTURE=')[1:]}
check('telemetry-log sequential recovery fixtures',
      hashlib.sha256((tlog_dir / 'control.tlog').read_bytes()).hexdigest() == recovery['source_sha256'] and
      all(hashlib.sha256((recovery_dir / name).read_bytes()).hexdigest() == info['sha256'] and
          (recovery_dir / name).stat().st_size == info['size'] for name, info in recovery['files'].items()) and
      'READ=0 BEFORE=0 AFTER=25 SIZE=50 LENGTH=17' in sections['two-valid.tlog'] and
      'READ=1 BEFORE=25 AFTER=50 SIZE=50 LENGTH=17' in sections['two-valid.tlog'] and
      'READ=0 BEFORE=0 AFTER=25 SIZE=50 LENGTH=0' in sections['bad-then-valid.tlog'] and
      'READ=1 BEFORE=25 AFTER=50 SIZE=50 LENGTH=17' in sections['bad-then-valid.tlog'] and
      'READ=0 BEFORE=0 AFTER=28 SIZE=53 LENGTH=17' in sections['noise-before-frame.tlog'] and
      'READ=1 BEFORE=28 AFTER=53 SIZE=53 LENGTH=17' in sections['noise-before-frame.tlog'] and
      'EndOfStreamException' in sections['noise-to-eof.tlog'] and
      'READ=0 BEFORE=0 AFTER=11 SIZE=11 LENGTH=0' in sections['noise-to-eof.tlog'],
      'One MAVLink 1 heartbeat in synthetic library fixtures; no general recovery or GUI claim.')
timestamp_dir = root / 'sitl-evidence/tlog-timestamp-probe'
timestamp = json.loads((timestamp_dir / 'fixtures.json').read_text())
timestamp_log = (timestamp_dir / 'probe.log').read_text(encoding='utf-16')
timestamp_sections = {section.splitlines()[0]: section for section in timestamp_log.split('FIXTURE=')[1:]}
first_time = 'UTC=2020-09-13T12:26:40.1230000Z'
second_time = 'UTC=2020-09-13T12:26:41.1240000Z'
check('telemetry-log timestamp fixtures',
      hashlib.sha256((tlog_dir / 'control.tlog').read_bytes()).hexdigest() == timestamp['control_sha256'] and
      timestamp['timestamp_us'] == [1600000000123456, 1600000001124690] and
      all(hashlib.sha256((timestamp_dir / name).read_bytes()).hexdigest() == info['sha256'] and
          (timestamp_dir / name).stat().st_size == info['size'] for name, info in timestamp['files'].items()) and
      'READ=0 POSITION=25 LENGTH=17 ' + first_time in timestamp_sections['timestamped.tlog'] and
      'READ=1 POSITION=50 LENGTH=17 ' + second_time in timestamp_sections['timestamped.tlog'] and
      'READ=0 POSITION=25 LENGTH=17 ' + second_time in timestamp_sections['backward.tlog'] and
      'READ=1 POSITION=50 LENGTH=17 ' + first_time in timestamp_sections['backward.tlog'] and
      all(timestamp_sections[name].count('LENGTH=17 UTC=0001-01-01T00:00:00.0000000Z') == 2
          for name in ('raw.rlog', 'raw.tlog')),
      'Specific library timestamp fixtures; GUI playback timing not tested.')
signature_dir = root / 'sitl-evidence/tlog-signature-probe'
signature = json.loads((signature_dir / 'fixtures.json').read_text())
signature_log = (signature_dir / 'probe.log').read_text(encoding='utf-16')
signature_sections = {section.splitlines()[0]: section for section in signature_log.split('FIXTURE=')[1:]}
sig_a = (signature_dir / 'arbitrary-signature-a.tlog').read_bytes()
sig_b = (signature_dir / 'arbitrary-signature-b.tlog').read_bytes()
check('telemetry-log signed-frame fixtures',
      hashlib.sha256((tlog_dir / 'control.tlog').read_bytes()).hexdigest() == signature['control_sha256'] and
      all(hashlib.sha256((signature_dir / name).read_bytes()).hexdigest() == info['sha256'] and
          (signature_dir / name).stat().st_size == info['size'] for name, info in signature['files'].items()) and
      sig_a[:-13] == sig_b[:-13] and sig_a[-13:] == bytes(13) and sig_b[-13:] == bytes([0x55] * 13) and
      all('VALIDATED LENGTH=34 MESSAGE=0 SYSTEM=255 POSITION=42 FILE_LENGTH=42' in signature_sections[name]
          for name in ('arbitrary-signature-a.tlog', 'arbitrary-signature-b.tlog')) and
      'crc fail' in signature_sections['payload-flipped.tlog'] and
      'VALIDATED LENGTH=0 MESSAGE=0 SYSTEM=0 POSITION=42 FILE_LENGTH=42' in signature_sections['payload-flipped.tlog'],
      'Playback with arbitrary signature blocks; no live-link signing or key-validation claim.')
param_file_dir = root / 'sitl-evidence/param-file-probe'
param_file_summary = json.loads((param_file_dir / 'summary.json').read_text())
param_file_log = (param_file_dir / 'probe.log').read_text(encoding='utf-16')
check('parameter-file library fixtures', param_file_summary['passed'] and
      all(param_file_summary['checks'].values()) and
      all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
          for name, digest in param_file_summary['sha256'].items()) and
      'normal.param KEY=NAN VALUE=NaN' in param_file_log and
      'bad-excluded.param EXCEPTION=System.FormatException' in param_file_log and
      'SAVED_READBACK COUNT=2' in param_file_log,
      'Synthetic files through the utility library; no UI or vehicle-write claim.')
nonfinite = json.loads((root / 'sitl-evidence/archive-copter-nonfinite-param/results.json').read_text())
check('exact-source Copter non-finite parameter writes', nonfinite['passed'] and not nonfinite['errors'] and
      nonfinite['binary_sha256'] == built_sha and all(value['passed'] for value in nonfinite['checks'].values()) and
      all(nonfinite['checks'][name]['out_of_range_error_seen'] and nonfinite['checks'][name]['readback'] == 0
          for name in ('nan', 'positive_infinity', 'negative_infinity')) and
      nonfinite['checks']['finite_control']['readback'] == 1 and nonfinite['checks']['restored']['readback'] == 0 and
      all(any(reply.get('type') == 'PARAM_ERROR' and reply.get('error') == 2 for reply in exchange['replies'])
          for exchange in nonfinite['exchanges'][:3]),
      'Standalone MAVLink 2 client and one disposable simulator parameter; no Mission Planner UI or physical-vehicle claim.')
mp_nonfinite_dir = root / 'sitl-evidence/missionplanner-nonfinite-probe'
mp_nonfinite = json.loads((mp_nonfinite_dir / 'summary.json').read_text())
mp_nonfinite_log = (mp_nonfinite_dir / 'probe.log').read_text(encoding='utf-16')
check('Mission Planner library non-finite parameter write', mp_nonfinite['passed'] and
      mp_nonfinite['binary_sha256'] == built_sha and all(mp_nonfinite['checks'].values()) and
      all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
          for name, digest in mp_nonfinite['sha256'].items()) and
      mp_nonfinite_log.count('Unknown Packet 345') == 4 and
      'NONFINITE_EXCEPTION=System.TimeoutException' in mp_nonfinite_log and
      all(token in mp_nonfinite_log for token in ('PARSED_NAN=True', 'AFTER_NONFINITE=0',
                                                  'FINITE_READBACK=1', 'RESTORE_READBACK=0')),
      'Original library and source-built SITL; packet 345 payload was not independently captured or decoded in this run.')
capture_dir = root / 'sitl-evidence/missionplanner-nonfinite-capture'
capture_proxy = json.loads((capture_dir / 'proxy-result.json').read_text())
capture = json.loads((capture_dir / 'decoded.json').read_text())
capture_log = (capture_dir / 'probe.log').read_text(encoding='utf-16')
capture_up = capture['directions']['uplink']['messages']
capture_down = capture['directions']['downlink']['messages']
check('captured Mission Planner non-finite parameter exchange', capture['passed'] and
      capture['binary_sha256'] == capture_proxy['binary_sha256'] == built_sha and
      all(capture['checks'].values()) and not capture_proxy['errors'] and capture_proxy['ended_by'] == 'client_eof' and
      all(hashlib.sha256((capture_dir / (direction + '.bin')).read_bytes()).hexdigest() ==
          capture_proxy[direction + '_sha256'] == capture['directions'][direction]['sha256'] and
          (capture_dir / (direction + '.bin')).stat().st_size == capture_proxy['bytes'][direction]
          for direction in ('uplink', 'downlink')) and
      capture['directions']['uplink']['bad_data_records'] == 0 and
      capture['directions']['downlink']['bad_data_reasons'] == {'Bad prefix': 53} and
      sum(row['type'] == 'PARAM_SET' and row.get('value') == 'NaN' for row in capture_up) == 4 and
      sum(row['type'] == 'PARAM_ERROR' and row.get('error') == 2 for row in capture_down) == 4 and
      capture_log.count('Unknown Packet 345') == 4 and 'NONFINITE_EXCEPTION=System.TimeoutException' in capture_log and
      'FINITE_READBACK=1' in capture_log and 'RESTORE_READBACK=0' in capture_log,
      'Passive localhost relay and offline MAVLink decode; no UI or physical-vehicle claim.')
mission_file_dir = root / 'sitl-evidence/mission-file-probe'
mission_file_summary = json.loads((mission_file_dir / 'summary.json').read_text())
mission_file_json = json.loads((mission_file_dir / 'generated.mission').read_text())
mission_file_log = (mission_file_dir / 'probe.log').read_text(encoding='utf-16')
check('mission-file library fixtures', mission_file_summary['passed'] and
      all(mission_file_summary['checks'].values()) and
      all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
          for name, digest in mission_file_summary['sha256'].items()) and
      mission_file_json['mission']['items'][0]['type'] is None and
      'JSON_READBACK COUNT=1' in mission_file_log and 'JSON_SIMPLE_CONTROL COUNT=2' in mission_file_log,
      'Synthetic files and original utility library; no GUI save-open or vehicle test.')
mission_plan_dir = root / 'sitl-evidence/mission-plan-probe'
mission_plan_summary = json.loads((mission_plan_dir / 'summary.json').read_text())
mission_plan_fixtures = json.loads((mission_plan_dir / 'fixtures.json').read_text())
mission_plan_log = (mission_plan_dir / 'probe.log').read_text(encoding='utf-16')
check('mission-plan conversion fixtures', mission_plan_summary['passed'] and
      all(mission_plan_summary['checks'].values()) and
      all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
          for name, digest in mission_plan_summary['sha256'].items()) and
      all(hashlib.sha256((mission_plan_dir / name).read_bytes()).hexdigest() == value['sha256'] and
          (mission_plan_dir / name).stat().st_size == value['size'] for name, value in mission_plan_fixtures.items()) and
      'COUNT=4' in mission_plan_log and 'EXCEPTION=System.NullReferenceException' in mission_plan_log and
      'EXCEPTION=System.ArgumentOutOfRangeException' in mission_plan_log,
      'Three synthetic plan inputs and library harness; no GUI error-handling claim.')
multivehicle_dir = root / 'sitl-evidence/multivehicle-parser-probe'
multivehicle = json.loads((multivehicle_dir / 'summary.json').read_text())
multivehicle_log = (multivehicle_dir / 'isolation.log').read_text(encoding='utf-16')
check('in-memory multi-vehicle parser fixtures', multivehicle['passed'] and
      all(multivehicle['checks'].values()) and
      all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
          for name, digest in multivehicle['sha256'].items()) and
      all(hashlib.sha256((multivehicle_dir / name).read_bytes()).hexdigest() == info['sha256'] and
          (multivehicle_dir / name).stat().st_size == info['size'] for name, info in multivehicle['fixtures'].items()) and
      all(token in multivehicle_log for token in ('SELECTED=255:190', 'PARAM=1:1 VALUE=12.5',
                                                   'PARAM=2:1 VALUE=87.5', 'PARAM=1:100 VALUE=42')),
      'Synthetic raw parser and timed in-memory Open; no real multi-vehicle connection.')
live_dir = root / 'sitl-evidence/live-signing-probe'
live_manifest = json.loads((live_dir / 'fixtures.json').read_text())
live_log = (live_dir / 'probe.log').read_text(encoding='utf-16')
live_sections = {section.splitlines()[0].split()[0]: section for section in live_log.split('CASE=')[1:]}
live_key = bytes.fromhex(live_manifest['test_key_hex'])
live_signed = (live_dir / 'signed.bin').read_bytes()
live_bad = (live_dir / 'bad-signature.bin').read_bytes()
check('in-memory MAVLink signing fixtures',
      hashlib.sha256((tlog_dir / 'control.tlog').read_bytes()).hexdigest() == live_manifest['control_sha256'] and
      live_key == bytes(range(32)) and len(live_signed) == 34 and live_signed[2] & 1 and
      hashlib.sha256(live_key + live_signed[:-6]).digest()[:6] == live_signed[-6:] and
      live_bad[:-1] == live_signed[:-1] and live_bad[-1] == live_signed[-1] ^ 1 and
      (live_dir / 'signed-twice.bin').read_bytes() == live_signed + live_signed and
      (live_dir / 'signed-then-unsigned.bin').read_bytes() == live_signed + (live_dir / 'unsigned.bin').read_bytes() and
      all(hashlib.sha256((live_dir / name).read_bytes()).hexdigest() == info['sha256'] and
          (live_dir / name).stat().st_size == info['size'] for name, info in live_manifest['files'].items()) and
      'READ=0 LENGTH=34 SYSTEM=1 COMPONENT=1 REMAINING=0' in live_sections['valid-key'] and
      'READ=0 LENGTH=0 SYSTEM=0 COMPONENT=0 REMAINING=0' in live_sections['bad-signature'] and
      'Packet failed signature but passed crc' in live_sections['bad-signature'] and
      'READ=0 LENGTH=34 SYSTEM=1 COMPONENT=1 REMAINING=0' in live_sections['ignore-bad'] and
      'READ=0 LENGTH=34 SYSTEM=1 COMPONENT=1 REMAINING=34' in live_sections['same-signed-twice'] and
      'READ=1 LENGTH=34 SYSTEM=1 COMPONENT=1 REMAINING=0' in live_sections['same-signed-twice'] and
      'READ=0 LENGTH=21 SYSTEM=1 COMPONENT=1 REMAINING=0' in live_sections['unsigned-while-signing'] and
      'READ=0 LENGTH=34 SYSTEM=1 COMPONENT=1 REMAINING=21 STATE_SIGNING=True' in live_sections['signed-then-unsigned'] and
      'READ=1 LENGTH=21 SYSTEM=1 COMPONENT=1 REMAINING=0 STATE_SIGNING=True' in live_sections['signed-then-unsigned'],
      'Synthetic key and in-memory parser, not a connected vehicle or full replay-protection assessment.')
sign_sitl_dir = root / 'sitl-evidence/command-ack-signing_sitl'
sign_sitl = json.loads((sign_sitl_dir / 'summary.json').read_text())
sign_relay = json.loads((sign_sitl_dir / 'relay-result.json').read_text())
def signature_matches(record, key):
    raw = bytes.fromhex(record['raw_hex'])
    return raw[0] == 253 and raw[2] & 1 and hashlib.sha256(key + raw[:-6]).digest()[:6] == raw[-6:]
sign_key = bytes.fromhex(sign_sitl['synthetic_key_hex'])
check('SITL synthetic MAVLink signing exchange',
      sign_sitl['relay'] == sign_relay and sign_relay['case'] == 'signing_sitl' and not sign_relay['errors'] and
      sign_relay['closed_by'] == 'client' and sign_relay['buffered_bytes_at_close'] == 0 and
      sign_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((sign_sitl_dir / n).read_bytes()).hexdigest() == digest for n,digest in sign_relay['capture_sha256'].items()) and
      all(hashlib.sha256((sign_sitl_dir / n).read_bytes()).hexdigest() == digest for n,digest in sign_sitl['hashes'].items()) and
      all(hashlib.sha256((root / 'mission-planner-portable' / n).read_bytes()).hexdigest() == digest for n,digest in sign_sitl['library_hashes'].items()) and
      (sign_sitl_dir / 'probe-exit.txt').read_text().strip() == '0' and sign_key == bytes(range(32)) and
      len(sign_sitl['setup']) == 2 and all(bytes(m['secret_key']) == sign_key and not m['signed'] for m in sign_sitl['setup']) and
      len(sign_sitl['requests']) == 2 and not sign_sitl['requests'][0]['signed'] and signature_matches(sign_sitl['requests'][1],sign_key) and
      any(m['signed'] and m['param_value'] == 0 and signature_matches(m,sign_key) for m in sign_sitl['responses']) and
      sign_sitl['heartbeats'] and all(not(m['base_mode'] & 128) for m in sign_sitl['heartbeats']) and
      any(m['signed'] and signature_matches(m,sign_key) for m in sign_sitl['heartbeats']) and
      len(sign_sitl['zero_key_status']) == 1 and signature_matches(sign_sitl['zero_key_status'][0],bytes(32)) and
      not signature_matches(sign_sitl['zero_key_status'][0],sign_key) and
      all(line in (sign_sitl_dir / 'probe.log').read_text(encoding='utf8',errors='replace') for line in
          ('BEFORE=0','SETUP_RETURN=True STATE_SIGNING=True','AFTER=0','SIGNING_SITL_COMPLETE=True')),
      'One disarmed SITL connection with public synthetic key and reflection-injected vehicle key; not normal key lookup or UI.')
channel_dir = root / 'sitl-evidence/signing-channel-sitl-2'
channel_summary = json.loads((channel_dir / 'summary.json').read_text())
channel_result = json.loads((channel_dir / 'result.json').read_text())
channel_first = root / 'sitl-evidence/signing-channel-sitl'
channel_initial = json.loads((channel_first / 'result.json').read_text())
channel_key = hashlib.sha256(b'synthetic-channel-signing-key').digest()
channel_wrong = hashlib.sha256(b'synthetic-channel-wrong-key').digest()
channel_expected = {'channel0/unsigned':1,'channel0/bad_signature':1,'channel0/valid':1,'channel0/replay':1,
                    'channel1/unsigned':0,'channel1/bad_signature':0,'channel1/valid':1,'channel1/replay':0}
import os, sys
sys.path.insert(0,str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega as signing_dialect
def channel_window(data):
    parser = signing_dialect.MAVLink(None); parser.robust_parsing = True; responses = []
    for byte in data:
        msg = parser.parse_char(bytes([byte]))
        if msg is not None and msg.get_type() == 'PARAM_VALUE' and msg.param_id == 'LOG_DISARMED' and [msg.get_srcSystem(),msg.get_srcComponent()] == [1,1]:
            responses.append(bytes(msg.get_msgbuf()).hex())
    return responses
channel_valid = True
for label,event in channel_summary['events'].items():
    ch,case = label.split('/')
    request = bytes.fromhex(event['request_hex'])
    uplink = (channel_dir / (ch+'-uplink.bin')).read_bytes()
    downlink = (channel_dir / (ch+'-downlink.bin')).read_bytes()
    channel_valid &= uplink[event['uplink_start']:event['uplink_end']] == request
    channel_valid &= channel_window(downlink[event['downlink_start']:event['downlink_end']]) == [m['raw_hex'] for m in event['responses']]
    channel_valid &= all(m['param_value'] == 0 and signature_matches(m,channel_key) for m in event['responses'])
    if case == 'unsigned': channel_valid &= request[0] == 253 and not(request[2] & 1)
    if case == 'bad_signature': channel_valid &= signature_matches({'raw_hex':request.hex()},channel_wrong) and not signature_matches({'raw_hex':request.hex()},channel_key)
    if case in ('valid','replay'): channel_valid &= signature_matches({'raw_hex':request.hex()},channel_key)
channel_source = root / 'ardupilot-source/ardupilot-master/libraries/GCS_MAVLink/GCS_Signing.cpp'
channel_source_data = channel_source.read_bytes()
channel_source_blob = hashlib.sha1(('blob ' + str(len(channel_source_data)) + '\0').encode()+channel_source_data).hexdigest()
check('SITL signing across two serial endpoints',
      not channel_initial['errors'] and not channel_result['errors'] and
      channel_summary['binary_sha256'] == channel_result['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      channel_summary['first_result_sha256'] == hashlib.sha256((channel_first / 'result.json').read_bytes()).hexdigest() and
      channel_summary['second_result_sha256'] == hashlib.sha256((channel_dir / 'result.json').read_bytes()).hexdigest() and
      all(hashlib.sha256((channel_first / n).read_bytes()).hexdigest() == d for n,d in channel_initial['capture_sha256'].items()) and
      channel_summary['captures'] == channel_result['capture_sha256'] and
      all(hashlib.sha256((channel_dir / n).read_bytes()).hexdigest() == d for n,d in channel_summary['captures'].items()) and
      all(not(m['base_mode'] & 128) for e in channel_result['events'] if e['case'] == 'initial' for m in e['heartbeats']) and
      {k:len(v['responses']) for k,v in channel_summary['events'].items()} == channel_expected and channel_valid and
      all(channel_summary['events'][ch+'/valid']['request_hex'] == channel_summary['events'][ch+'/replay']['request_hex'] for ch in ('channel0','channel1')) and
      channel_source_blob == '8faffa7894bec6f3c2cdffd2172ee18986193b76' and
      'accept_unsigned_callback' in channel_source.read_text() and 'mavlink_get_channel_status(MAVLINK_COMM_0)' in channel_source.read_text(),
      'Two disarmed disposable SITL runs; standalone client, one read-only message, 1.5-second windows; internal channel assignment not instrumented.')
sign_rea = json.loads((root / 'mission-planner-binary-evidence/rea-ardupilot-all-members.json').read_text())['normalized_result']
for discovery_case in ('match','missing'):
    discovery_dir = root / 'sitl-evidence' / ('command-ack-signing_discovery_' + discovery_case)
    discovery = json.loads((discovery_dir / 'summary.json').read_text())
    discovery_relay = json.loads((discovery_dir / 'relay-result.json').read_text())
    discovery_key = hashlib.sha256(b'synthetic-signing-seed').digest()
    wrong_key = hashlib.sha256(b'synthetic-wrong-key').digest()
    discovery_log = (discovery_dir / 'probe.log').read_text(encoding='utf8',errors='replace')
    check('SITL synthetic signing discovery ' + discovery_case,
          discovery['relay'] == discovery_relay and discovery_relay['case'] == 'signing_discovery_' + discovery_case and
          not discovery_relay['errors'] and discovery_relay['closed_by'] == 'client' and discovery_relay['buffered_bytes_at_close'] == 0 and
          discovery_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((discovery_dir / n).read_bytes()).hexdigest() == d for n,d in discovery_relay['capture_sha256'].items()) and
          all(hashlib.sha256((discovery_dir / n).read_bytes()).hexdigest() == d for n,d in discovery['hashes'].items()) and
          all(hashlib.sha256((root / 'mission-planner-portable' / n).read_bytes()).hexdigest() == d for n,d in discovery['library_hashes'].items()) and
          (discovery_dir / 'probe-exit.txt').read_text().strip() == '0' and
          bytes.fromhex(discovery['synthetic_test_key_hex']) == discovery_key and bytes.fromhex(discovery['synthetic_wrong_key_hex']) == wrong_key and
          len(discovery['setup']) == 2 and all(bytes(m['secret_key']) == discovery_key and not m['signed'] for m in discovery['setup']) and
          discovery['heartbeats'] and all(not(m['base_mode'] & 128) for m in discovery['heartbeats']) and
          any(m['signed'] and signature_matches(m,discovery_key) for m in discovery['heartbeats']) and
          any(m['signed'] and m['param_value'] == 0 and signature_matches(m,discovery_key) for m in discovery['responses']) and
          all(x in discovery_log for x in ('BEFORE=0','SETUP=True STATE_KEY_NULL=True','DISCOVERY_PROBE_COMPLETE=True')) and
          ((discovery_case == 'match' and all(x in discovery_log for x in ('CASE=match KEY_CANDIDATES=2','ADOPTED=True KEY_NULL=False','AFTER=0')) and
            any(m['signed'] and signature_matches(m,discovery_key) for m in discovery['requests'])) or
           (discovery_case == 'missing' and all(x in discovery_log for x in ('CASE=missing KEY_CANDIDATES=1','ADOPTED=False KEY_NULL=True','AFTER_ERROR=System.TimeoutException:Timeout on read - GetParam','Packet failed signature but passed crc')) and
            any(m['signed'] and signature_matches(m,bytes(32)) and not signature_matches(m,discovery_key) for m in discovery['requests']))),
          'Disposable SITL and isolated synthetic registry; match adopts key, wrong-only case times out despite captured signed responses.')
for serial_case in ('match','missing'):
    serial_dir = root / 'sitl-evidence' / ('signing-serial1-' + serial_case)
    serial = json.loads((serial_dir / 'summary.json').read_text())
    serial_relay = json.loads((serial_dir / 'relay-result.json').read_text())
    serial_log = (serial_dir / 'probe.log').read_text(encoding='utf8',errors='replace')
    serial_key = hashlib.sha256(b'synthetic-signing-seed').digest()
    serial_setup = serial['setup']
    serial_hb = serial['heartbeats']
    check('SITL signed SERIAL1 library ' + serial_case,
          serial['relay'] == serial_relay and serial_relay['case'] == serial_case and not serial_relay['errors'] and serial_relay['closed_by'] == 'client' and
          serial_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          serial_relay['test_key_hex'] == serial_key.hex() and
          all(hashlib.sha256((serial_dir / n).read_bytes()).hexdigest() == d for n,d in serial_relay['capture_sha256'].items()) and
          all(hashlib.sha256((serial_dir / n).read_bytes()).hexdigest() == d for n,d in serial['hashes'].items()) and
          all(hashlib.sha256((root / 'mission-planner-portable' / n).read_bytes()).hexdigest() == d for n,d in serial['library_hashes'].items()) and
          (serial_dir / 'probe-exit.txt').read_text().strip() == '0' and
          len(serial_setup) == 1 and serial_setup[0]['mavpackettype'] == 'SETUP_SIGNING' and bytes(serial_setup[0]['secret_key']) == serial_key and
          all(any(m['mavpackettype'] == 'HEARTBEAT' and m['signed'] and signature_matches(m,serial_key) for m in serial[name]) for name in ('bootstrap_primary','bootstrap_secondary')) and
          serial_hb and all(m['signed'] and signature_matches(m,serial_key) and not(m['base_mode'] & 128) for m in serial_hb) and
          ((serial_case == 'match' and all(x in serial_log for x in ('CASE=match CANDIDATES=2','OPEN_RETURNED=True ISOPEN=True SELECTED=1:1','ADOPTED=True KEY_NULL=False','PARAM=0','SERIAL1_PROBE_COMPLETE=True')) and
            serial['requests'] and all(m['signed'] and signature_matches(m,serial_key) for m in serial['requests']) and
            any(m['signed'] and m['param_value'] == 0 and signature_matches(m,serial_key) for m in serial['responses'])) or
           (serial_case == 'missing' and all(x in serial_log for x in ('CASE=missing CANDIDATES=1','OPEN_RETURNED=True ISOPEN=False SELECTED=0:0','ADOPTED=False KEY_NULL=True','Packet failed signature but passed crc','System.InvalidOperationException: Sequence contains no elements','SERIAL1_PROBE_COMPLETE=True')) and
            not serial['requests'] and not serial['responses'])),
          'One disarmed simulator per case; synthetic key bootstrap on SERIAL0, original Mission Planner library via local SERIAL1 relay.')
replay_dir = root / 'sitl-evidence/signing-serial1-replay-match'
replay = json.loads((replay_dir / 'summary.json').read_text())
replay_relay = json.loads((replay_dir / 'relay-result.json').read_text())
replay_log = (replay_dir / 'probe.log').read_text(encoding='utf8',errors='replace')
replay_key = hashlib.sha256(b'synthetic-signing-seed').digest()
replay_sample = bytes.fromhex(replay_relay['configured_secondary']['raw_hex'])
replay_bad = replay_sample[:-1] + bytes([replay_sample[-1] ^ 1])
check('SITL signed heartbeat replay into Mission Planner library',
      replay['relay'] == replay_relay and replay_relay['case'] == 'match' and not replay_relay['errors'] and replay_relay['closed_by'] == 'client' and
      replay_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      replay_relay['test_key_hex'] == replay_key.hex() and
      all(hashlib.sha256((replay_dir / n).read_bytes()).hexdigest() == d for n,d in replay_relay['capture_sha256'].items()) and
      all(hashlib.sha256((replay_dir / n).read_bytes()).hexdigest() == d for n,d in replay['hashes'].items()) and
      all(hashlib.sha256((root / 'mission-planner-portable' / n).read_bytes()).hexdigest() == d for n,d in replay['library_hashes'].items()) and
      (replay_dir / 'probe-exit.txt').read_text().strip() == '0' and
      signature_matches({'raw_hex':replay_sample.hex()},replay_key) and not signature_matches({'raw_hex':replay_bad.hex()},replay_key) and
      replay_sample in (replay_dir / 'bootstrap-secondary-down.bin').read_bytes() and
      (replay_dir / 'injected.bin').read_bytes() == replay_sample+replay_sample+replay_bad and
      (replay_dir / 'downlink.bin').read_bytes().startswith(replay_sample+replay_sample+replay_bad) and
      replay['sample_sha256'] == replay_relay['injected_sample_sha256'] == hashlib.sha256(replay_sample).hexdigest() and
      replay['bad_sha256'] == replay_relay['injected_bad_sha256'] == hashlib.sha256(replay_bad).hexdigest() and
      replay['sample_event_count'] == replay_log.count('HB_SHA='+replay['sample_sha256']) == 2 and
      replay['bad_event_count'] == replay_log.count('HB_SHA='+replay['bad_sha256']) == 0 and
      replay['signature_failure_log_count'] == replay_log.count('Packet failed signature but passed crc') >= 1 and
      all(x in replay_log for x in ('OPEN_RETURNED=True ISOPEN=True SELECTED=1:1','ADOPTED=True KEY_NULL=False','PARAM=0','SERIAL1_PROBE_COMPLETE=True')),
      'One disarmed SITL heartbeat over local relay; two identical accepted events and one altered-signature failure, not full-app replay assessment.')
sign_methods = [m for m in sign_rea['methods'] if m['declaring_type'] == 'MissionPlanner.MAVLinkInterface' and m['name'] in ('setupSigning','CheckSignature')]
check('REA MAVLink signing method records',
      sign_rea['artifact']['sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      {(m['name'],m['token']) for m in sign_methods} == {('setupSigning','0x0600043e'),('CheckSignature','0x06000498')} and
      all(m['body']['status'] == 'present' and len(m['body']['il_sha256']) == 64 for m in sign_methods),
      'REA metadata and method IL hashes for distributed assembly; no source equivalence claim.')
remaining_summary_file = root / 'mission-planner-binary-evidence/rea-remaining-index-summary.json'
for accord_name in ('accord-statistics', 'accord-vision', 'system-reactive', 'ironpython', 'sixlabors-imagesharp', 'alglibnet', 'xamarin-forms-core', 'bouncycastle-cryptography', 'microsoft-codeanalysis', 'microsoft-codeanalysis-csharp'):
    accord_dir = root / 'mission-planner-binary-evidence' / (accord_name + '-batches')
    accord_index_summary = accord_dir / 'index-summary.json'
    if not accord_index_summary.exists():
        raise FileNotFoundError(accord_index_summary)
    summary = json.loads(accord_index_summary.read_text())
    coverage_file = accord_dir / 'coverage-summary.json'
    coverage = json.loads(coverage_file.read_text())
    database = accord_dir / 'index.sqlite'
    with sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True) as connection:
        counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                  for table in ('types', 'methods', 'calls')}
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    check(accord_name + ' recovered member index integrity', coverage['complete'] and
          coverage['assembly_sha256'] == summary['assembly_sha256'] and
          hashlib.sha256(coverage_file.read_bytes()).hexdigest() == summary['coverage_summary_sha256'] and
          hashlib.sha256((accord_dir / 'manifest.json').read_bytes()).hexdigest() == summary['manifest_sha256'] and
          hashlib.sha256(database.read_bytes()).hexdigest() == summary['database_sha256'] and
          counts == summary['counts'] and integrity == 'ok' and
          counts['types'] == coverage['expected_types'] and counts['methods'] == coverage['expected_methods'],
          'Static member recovery compared with Cecil metadata; no runtime behavior claim.')
for partial_name in ('accord-math', 'opentk'):
    partial_dir = root / 'mission-planner-binary-evidence' / (partial_name + '-batches')
    partial_summary = json.loads((partial_dir / 'index-partial-summary.json').read_text())
    partial_coverage_file = partial_dir / 'coverage-summary.json'
    partial_coverage = json.loads(partial_coverage_file.read_text())
    partial_database = partial_dir / 'index-partial.sqlite'
    with sqlite3.connect(f'file:{partial_database.as_posix()}?mode=ro', uri=True) as connection:
        partial_counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                          for table in ('types', 'methods', 'calls')}
        partial_integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    check(partial_name + ' partial REA index integrity', not partial_summary['complete'] and not partial_coverage['complete'] and
          partial_coverage['partial_batches'] > 0 and
          hashlib.sha256(partial_database.read_bytes()).hexdigest() == partial_summary['database_sha256'] and
          hashlib.sha256(partial_coverage_file.read_bytes()).hexdigest() == partial_summary['coverage_summary_sha256'] and
          hashlib.sha256((partial_dir / 'manifest.json').read_bytes()).hexdigest() == partial_summary['manifest_sha256'] and
          partial_counts == partial_summary['counts'] and partial_counts['types'] == partial_coverage['observed_types'] and
          partial_counts['methods'] == partial_coverage['observed_methods'] and partial_integrity == 'ok',
          'Only complete REA batches indexed; partial selections remain excluded.')
cecil_dir = root / 'mission-planner-binary-evidence/remaining-managed-members'
for slug, binary, methods in (('accord-math-core', 'Accord.Math.Core.dll', 10540),
                              ('accord-math', 'Accord.Math.dll', 12532),
                              ('opentk', 'OpenTK.dll', 33436),
                              ('bouncycastle-cryptography', 'BouncyCastle.Cryptography.dll', 21095),
                              ('microsoft-codeanalysis', 'Microsoft.CodeAnalysis.dll', 16043),
                              ('microsoft-codeanalysis-csharp', 'Microsoft.CodeAnalysis.CSharp.dll', 37576)):
    cecil_summary = json.loads((cecil_dir / (slug + '-cecil-index-summary.json')).read_text())
    cecil_database = cecil_dir / (slug + '-cecil-index.sqlite')
    cecil_types = cecil_dir / (slug + '-cecil-types.tsv')
    cecil_capture = cecil_dir / (slug + '-cecil-methods.tsv.gz')
    with sqlite3.connect(f'file:{cecil_database.as_posix()}?mode=ro', uri=True) as connection:
        cecil_counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                        for table in ('methods', 'method_references')}
        cecil_integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    check(slug + ' Cecil fallback index',
          hashlib.sha256((root / 'mission-planner-portable' / binary).read_bytes()).hexdigest() == cecil_summary['assembly_sha256'] and
          hashlib.sha256(cecil_types.read_bytes()).hexdigest() == cecil_summary['type_inventory_sha256'] and
          hashlib.sha256(cecil_capture.read_bytes()).hexdigest() == cecil_summary['capture_sha256'] and
          hashlib.sha256(cecil_database.read_bytes()).hexdigest() == cecil_summary['database_sha256'] and
          cecil_counts == cecil_summary['counts'] and cecil_counts['methods'] == methods and cecil_integrity == 'ok',
          'Cecil fallback; REA remains partial and method-reference instructions are not runtime call evidence.')
remaining_db = root / 'mission-planner-binary-evidence/rea-remaining-index.sqlite'
if remaining_summary_file.exists():
    summary = json.loads(remaining_summary_file.read_text())
    with sqlite3.connect(f'file:{remaining_db.as_posix()}?mode=ro', uri=True) as connection:
        counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                  for table in ('assemblies', 'types', 'methods', 'calls')}
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    check('remaining managed member index snapshot',
          hashlib.sha256(remaining_db.read_bytes()).hexdigest() == summary['database_sha256'] and
          counts == summary['counts'] and integrity == 'ok' and
          counts['assemblies'] + len(summary['partial']) + len(summary['not_yet_processed']) == summary['requested'],
          'A point-in-time index of complete REA results; partial and unprocessed assemblies are excluded.')
mod_file = root / 'mission-planner-binary-evidence/rea-raised-budget-modification.json'
mod = json.loads(mod_file.read_text())
orig_code = (root / 'research-tools/node_modules/rea-agents' / mod['source_file']).read_bytes()
mod_code = (root / 'research-tools/node_modules/rea-agents-raised-budget' / mod['source_file']).read_bytes()
old = b'MAX_METADATA_REPRESENTATION_BYTES = 64 * 1024 * 1024;'
new = b'MAX_METADATA_REPRESENTATION_BYTES = 256 * 1024 * 1024;'
check('REA raised-budget modification', orig_code.count(old) == 1 and orig_code.replace(old, new, 1) == mod_code and
      hashlib.sha256(orig_code).hexdigest() == mod['original_sha256'] and
      hashlib.sha256(mod_code).hexdigest() == mod['modified_sha256'],
      'Only the CLI managed representation budget was changed in the copied file; other package files are not rehashed here.')
variant_dir = root / 'mission-planner-binary-evidence/rea-raised-budget'
variant_comparison = json.loads((variant_dir / 'variant-comparison.json').read_text())
variant_captures = {name: (variant_dir / (name + '-gaussian.json')).read_bytes()
                    for name in ('rea-agents', 'rea-agents-raised-budget')}
check('REA tool variant sample comparison', variant_comparison['normalized_results_equal'] and
      variant_comparison['coverage']['state'] == 'complete' and
      all(hashlib.sha256(data).hexdigest() == variant_comparison['capture_sha256'][name]
          for name, data in variant_captures.items()) and
      json.loads(variant_captures['rea-agents'])['normalized_result'] ==
      json.loads(variant_captures['rea-agents-raised-budget'])['normalized_result'],
      'One bounded selection matches; this is not proof of tool equivalence for larger selections.')
for slug in ('accord-math-core', 'accord-math', 'opentk'):
    mixed = root / 'mission-planner-binary-evidence' / (slug + '-mixed-batches')
    original = root / 'mission-planner-binary-evidence' / (slug + '-batches')
    manifest_file = mixed / 'manifest.json'
    manifest = json.loads(manifest_file.read_text())
    coverage_file = mixed / 'coverage-summary.json'
    coverage = json.loads(coverage_file.read_text())
    index_summary = json.loads((mixed / 'index-summary.json').read_text())
    database = mixed / 'index.sqlite'
    with sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True) as connection:
        mixed_counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                        for table in ('types', 'methods', 'calls')}
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    variants = {row['tool_variant'] for row in manifest['batches']}
    evidence_matches = all(
        hashlib.sha256((mixed / row['evidence']).read_bytes()).digest() ==
        hashlib.sha256(((original / row['evidence']) if row['tool_variant'] == 'original' else
                        (root / 'mission-planner-binary-evidence/rea-raised-budget' / row['evidence'][len('raised-'):])).read_bytes()).digest()
        for row in manifest['batches'])
    check(slug + ' mixed REA index integrity', coverage['complete'] and variants == {'original', 'raised-budget'} and
          evidence_matches and
          manifest['source_manifest_sha256'] == hashlib.sha256((original / 'manifest.json').read_bytes()).hexdigest() and
          manifest['modification_sha256'] == hashlib.sha256(mod_file.read_bytes()).hexdigest() and
          hashlib.sha256(manifest_file.read_bytes()).hexdigest() == index_summary['manifest_sha256'] and
          hashlib.sha256(coverage_file.read_bytes()).hexdigest() == index_summary['coverage_summary_sha256'] and
          hashlib.sha256(database.read_bytes()).hexdigest() == index_summary['database_sha256'] and
          mixed_counts == index_summary['counts'] and mixed_counts['types'] == coverage['expected_types'] and
          mixed_counts['methods'] == coverage['expected_methods'] and integrity == 'ok',
          'Combined original and raised-budget REA captures compared with Cecil metadata; static only.')
dual_dir = root / 'sitl-evidence/dual-sitl-library-attempt3'
dual = json.loads((dual_dir / 'summary.json').read_text())
dual_relay = json.loads((dual_dir / 'relay-result.json').read_text())
dual_log = (dual_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
check('dual SITL Mission Planner library relay',
      dual_relay == dual['relay'] and dual_relay['errors'] == [] and dual_relay['ended_by'] == 'client_eof' and
      all(hashlib.sha256((dual_dir / name).read_bytes()).hexdigest() == digest for name, digest in dual_relay['sha256'].items()) and
      all(line in dual_log for line in dual['verified_probe_lines']) and dual['heartbeat_systems'] == [1, 2] and
      {(p['source_system'], p['param_value']) for p in dual['parameter_responses']} >= {(1, 0.0), (2, 1.0), (2, 0.0)} and
      any(p['mavpackettype'] == 'PARAM_SET' and p['target_system'] == 2 and p['param_value'] == 0 for p in dual['requests']),
      'Two local SITLs through a frame-aware relay; not a real aircraft or full GUI test.')
org_capture = root / 'mission-planner-binary-evidence/ardupilot-org-repos-2026-11-05.json'
org_repos = [repo for page in json.loads(org_capture.read_text(encoding='utf-8-sig')) for repo in page]
org_document = (root / 'ArduPilot-Organization-Inventory.md').read_text(encoding='utf-8')
check('ArduPilot organization metadata snapshot',
      len(org_repos) == 86 and len({repo['id'] for repo in org_repos}) == len(org_repos) and
      all(repo['owner']['login'].lower() == 'ardupilot' and not repo['private'] for repo in org_repos) and
      hashlib.sha256(org_capture.read_bytes()).hexdigest() in org_document and
      all(repo['html_url'] in org_document for repo in org_repos),
      'Dated public metadata inventory; not a review of repository code.')
native_dir = root / 'mission-planner-binary-evidence/managed-native-all'
native_manifest_file = native_dir / 'manifest.json'
native_manifest = json.loads(native_manifest_file.read_text())
native_summary = json.loads((native_dir / 'index-summary.json').read_text())
native_db = native_dir / 'index.sqlite'
with sqlite3.connect(f'file:{native_db.as_posix()}?mode=ro', uri=True) as connection:
    native_counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                     for table in ('assemblies', 'imports', 'native_implementations')}
    native_integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
check('all managed native boundary inventory',
      native_manifest['requested'] == len(native_manifest['results']) == 260 and
      native_manifest['input_sha256'] == hashlib.sha256((root / 'mission-planner-binary-evidence/all-managed-identities/manifest.json').read_bytes()).hexdigest() and
      all(row.get('exit_code') == 0 and row.get('coverage', {}).get('state') == 'complete' and
          hashlib.sha256((native_dir / row['evidence']).read_bytes()).hexdigest() == row['evidence_sha256']
          for row in native_manifest['results']) and
      hashlib.sha256(native_manifest_file.read_bytes()).hexdigest() == native_summary['manifest_sha256'] and
      hashlib.sha256(native_db.read_bytes()).hexdigest() == native_summary['database_sha256'] and
      native_counts == native_summary['counts'] and native_summary['coverage'] == {'complete': 260} and native_integrity == 'ok',
      'Static REA managed declarations, not runtime native loading.')
match_summary = json.loads((native_dir / 'native-name-matches-summary.json').read_text())
match_db = native_dir / 'native-name-matches.sqlite'
with sqlite3.connect(f'file:{match_db.as_posix()}?mode=ro', uri=True) as connection:
    match_count = connection.execute('SELECT COUNT(*) FROM matches').fetchone()[0]
    match_exact = connection.execute('SELECT COUNT(*) FROM matches WHERE exact_export=1').fetchone()[0]
    match_integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
check('native import export name candidates',
      match_summary['boundary_index_sha256'] == hashlib.sha256(native_db.read_bytes()).hexdigest() and
      match_summary['native_manifest_sha256'] == hashlib.sha256((root / 'mission-planner-binary-evidence/native-exports/manifest.json').read_bytes()).hexdigest() and
      match_summary['database_sha256'] == hashlib.sha256(match_db.read_bytes()).hexdigest() and
      match_count == match_summary['candidate_rows'] and match_exact == match_summary['exact_name_rows'] and match_integrity == 'ok',
      'Basename and exact export-name candidates only; architecture, suffix probing and runtime resolution unverified.')
ogr_input = json.loads((native_dir / 'ogr-rea-verification-input.json').read_text(encoding='utf-8'))
ogr_output = json.loads((native_dir / 'ogr-rea-verification-output.json').read_text())['normalized_result']
check('REA PE native verification limitation',
      ogr_output['managed_boundary']['evidence_id'] == ogr_input['managed_boundaries']['evidence_id'] and
      ogr_output['managed_boundary']['pinvoke_imports_total'] == 421 and
      ogr_output['native_observations'] == {'total': 2, 'accepted': 0, 'unsupported': 2, 'symbols': 0} and
      ogr_output['summary']['verified'] == 0 and ogr_output['summary']['unresolved'] == 421 and
      ogr_output['coverage']['status'] == 'partial',
      'REA rejected both supplied PE export records; the separate name match is not this verifier.')
selection_log = (root / 'sitl-evidence/multivehicle-parser-probe/selection-events.log').read_text(encoding='utf-16')
selection_state_log = (root / 'sitl-evidence/multivehicle-parser-probe/selection-events-state.log').read_text(encoding='utf-16')
selection_clear_log = (root / 'sitl-evidence/multivehicle-parser-probe/selection-events-clear.log').read_text(encoding='utf-16')
selection_playback_log = (root / 'sitl-evidence/multivehicle-parser-probe/selection-events-playback.log').read_text(encoding='utf-16')
check('vehicle selection change events', selection_log.splitlines() ==
      ['EVENT=2:100', 'EVENT=2:1', 'FINAL=2:1 EVENTS=2'] and selection_state_log.splitlines() ==
      ['EVENT=2:100', 'STATE=2:100', 'EVENT=2:1', 'STATE=2:1', 'FINAL=2:1 EVENTS=2',
       'INTERMEDIATE_HIDDEN=True INTERMEDIATE_VISIBLE=False'] and selection_clear_log.splitlines() ==
      selection_state_log.splitlines() + ['AFTER_CLEAR_HIDDEN=True AFTER_CLEAR_VISIBLE=False'] and
      selection_playback_log.splitlines() == selection_clear_log.splitlines() +
      ['AFTER_PLAYBACK_SET_HIDDEN=True AFTER_PLAYBACK_SET_VISIBLE=False'],
      'Property-only original library harness; no UI subscriber or vehicle behavior claim.')
source_index = INTEGRATION_DIR / 'ardupilot-source-index.sqlite'
source_summary = json.loads((source_index.parent / 'ardupilot-source-index-summary.json').read_text())
with sqlite3.connect(f'file:{source_index.as_posix()}?mode=ro', uri=True) as connection:
    source_counts = dict(connection.execute('SELECT status, COUNT(*) FROM files GROUP BY status'))
    indexed_count = connection.execute('SELECT COUNT(*) FROM source_text').fetchone()[0]
    source_integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    sample_count = connection.execute('SELECT COUNT(*) FROM source_text WHERE source_text MATCH ? AND path=?',
                                      ('SYSID', 'libraries/GCS_MAVLink/GCS.cpp')).fetchone()[0]
check('ArduPilot source text index',
      source_summary['commit'] == '72b238201f5ea3b556e3809b2ec704fcf701474a' and
      hashlib.sha256(source_index.read_bytes()).hexdigest() == source_summary['database_sha256'] and
      source_counts == source_summary['status_counts'] and indexed_count == source_counts['indexed'] == 7309 and
      sum(source_counts.values()) == 8475 and source_integrity == 'ok' and sample_count == 1,
      'Tracked main Git tree only; indexed bytes matched blob hashes when captured, with listed exclusions.')
for source_slug, expected_count in (('mission-planner', 2973), ('mission-planner-normalized', 6020)):
    source_path = INTEGRATION_DIR / (source_slug + '-source-index.sqlite')
    source_data = json.loads((source_path.parent / (source_slug + '-source-index-summary.json')).read_text())
    with sqlite3.connect(f'file:{source_path.as_posix()}?mode=ro', uri=True) as connection:
        counts = dict(connection.execute('SELECT status, COUNT(*) FROM files GROUP BY status'))
        rows = connection.execute('SELECT COUNT(*) FROM source_text').fetchone()[0]
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        sample = connection.execute('SELECT COUNT(*) FROM source_text WHERE source_text MATCH ? AND path=?',
                                    ('MavChanged', 'MainV2.cs')).fetchone()[0]
    check(source_slug + ' source text index',
          source_data['commit'] == 'b78a7495fec69793f2fcc13be4b6a3d9e06b3e4e' and
          hashlib.sha256(source_path.read_bytes()).hexdigest() == source_data['database_sha256'] and
          source_data['status_counts'] == counts and rows == expected_count and
          rows == counts.get('indexed', 0) + counts.get('indexed-crlf-normalized', 0) and
          integrity == 'ok' and (sample == 1 if source_slug.endswith('-normalized') else True),
          'Git blob-matched UTF-8 source snapshot; normalized variant records CRLF-to-LF matches separately.')
sub_index = INTEGRATION_DIR / 'ardupilot-submodules-index.sqlite'
sub_summary = json.loads((sub_index.parent / 'ardupilot-submodules-index-summary.json').read_text())
sub_names = {'modules/waf':'waf', 'modules/mavlink':'mavlink', 'modules/mavlink/pymavlink':'pymavlink',
             'modules/DroneCAN/DSDL':'dsdl', 'modules/DroneCAN/dronecan_dsdlc':'dsdlc',
             'modules/DroneCAN/libcanard':'libcanard', 'modules/DroneCAN/pydronecan':'pydronecan',
             'modules/littlefs':'littlefs', 'modules/ChibiOS':'chibios', 'modules/gbenchmark':'gbenchmark',
             'modules/gsoap':'gsoap', 'modules/gtest':'gtest', 'modules/lwip':'lwip',
             'modules/Micro-CDR':'microcdr', 'modules/Micro-XRCE-DDS-Client':'microxrce',
             'modules/DroneCAN/libcanard/drivers/avr/avr-can-lib':'avrcan'}
sub_tree_hashes = {path: hashlib.sha256((root / 'research-tools/submodule-archives' / (name + '-tree.json')).read_bytes()).hexdigest()
                   for path, name in sub_names.items()}
with sqlite3.connect(f'file:{sub_index.as_posix()}?mode=ro', uri=True) as connection:
    sub_counts = dict(connection.execute('SELECT status, COUNT(*) FROM files GROUP BY status'))
    sub_rows = connection.execute('SELECT COUNT(*) FROM source_text').fetchone()[0]
    sub_sample = connection.execute('SELECT COUNT(*) FROM source_text WHERE source_text MATCH ? AND path LIKE ?',
                                    ('HEARTBEAT', 'modules/mavlink/%')).fetchone()[0]
    sub_integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
check('ArduPilot submodule source text index',
      sub_summary['source_manifest_sha256'] == hashlib.sha256((root / 'ardupilot-source/extracted-submodules.json').read_bytes()).hexdigest() and
      hashlib.sha256(sub_index.read_bytes()).hexdigest() == sub_summary['database_sha256'] and
      sub_summary['status_counts'] == sub_counts and sub_rows == sub_counts['indexed'] == 15494 and
      sum(sub_counts.values()) == 16900 and sub_summary['tree_sha256'] == sub_tree_hashes and
      sub_sample > 0 and sub_integrity == 'ok',
      'Saved pinned submodule tree snapshots; per-file blob matches at capture, with listed exclusions.')
tcp_dir = root / 'sitl-evidence/tcp-reconnect-probe'
tcp_peer = json.loads((tcp_dir / 'peer-result.json').read_text())
tcp_log = (tcp_dir / 'probe.log').read_text(encoding='utf-16').splitlines()
check('TCP graceful close and explicit reopen fixture',
      tcp_peer['errors'] == [] and tcp_peer['events'] == ['first_accept', 'first_received=58', 'first_fin_sent',
          'first_client_eof', 'second_accept', 'second_client_eof'] and
      tcp_log == ['FIRST=FIRST', 'AFTER_FIN_BEFORE_READ_OPEN=True', 'EOF_READ=0', 'AFTER_EOF_OPEN=True',
                  'AFTER_CLOSE_OPEN=False HOST_EMPTY=True', 'SECOND=SECOND', 'REOPENED=True'],
      'Synthetic local peer; does not test automatic reconnect, GUI or a vehicle.')
auto_dir = root / 'sitl-evidence/tcp-autoreconnect-probe'
auto_peer = json.loads((auto_dir / 'peer-result.json').read_text())
auto_log = (auto_dir / 'probe.log').read_text(encoding='utf-16').splitlines()
check('TCP reset and automatic reconnect fixture',
      auto_peer['errors'] == [] and auto_peer['events'] == ['first_accept', 'first_received=58', 'first_reset',
          'second_accept', 'second_client_eof'] and
      auto_log == ['FIRST=FIRST', 'BEFORE_RESET_READ_OPEN=True', 'RESET_READ_ERROR=Socket Closed',
                   'AUTO_CONNECTED=True', 'SECOND=SECOND'],
      'Synthetic peer, reset and IsOpen polling; no MAVLink session or full application.')
offset_dir = root / 'sitl-evidence/tcp-write-offset-probe'
offset_peer = json.loads((offset_dir / 'peer-result.json').read_text())
offset_log = (offset_dir / 'probe.log').read_text(encoding='utf-16').splitlines()
check('TCP write buffer offset fixture', offset_peer['errors'] == [] and
      offset_peer['bytes_hex'] == '414243' and offset_peer['ascii'] == 'ABC' and
      offset_log == ['REQUESTED_OFFSET=2 LENGTH=3 EXPECTED_SLICE=CDE'],
      'Synthetic local TCP peer; no affected full-application workflow established.')
write_reset_dir = root / 'sitl-evidence/tcp-reset-write-probe'
write_reset_peer = json.loads((write_reset_dir / 'peer-result.json').read_text())
write_reset_log = (write_reset_dir / 'probe.log').read_text(encoding='utf-16').splitlines()
check('TCP write after reset fixture', write_reset_peer['errors'] == [] and
      write_reset_peer['events'] == ['accepted', 'marker=58', 'reset'] and
      write_reset_log == ['FIRST=FIRST', 'BEFORE_WRITE_OPEN=True', 'WRITE_RETURNED', 'AFTER_WRITE_OPEN=False'],
      'Synthetic local reset; no command acknowledgement or full-application behavior established.')
reconnect_dir = root / 'sitl-evidence/mavlink-reconnect-probe'
reconnect = json.loads((reconnect_dir / 'summary.json').read_text())
reconnect_relay = json.loads((reconnect_dir / 'relay-result.json').read_text())
reconnect_log = (reconnect_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
check('SITL MAVLink explicit reconnect fixture', reconnect['relay'] == reconnect_relay and
      reconnect_relay['errors'] == [] and reconnect_relay['events'] ==
      ['session1_accept', 'session1_reset', 'session2_accept', 'session2_client_eof'] and
      reconnect_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((reconnect_dir / name).read_bytes()).hexdigest() == digest
          for name, digest in reconnect_relay['captures_sha256'].items()) and
      all(line in reconnect_log for line in reconnect['verified_probe_lines']) and
      len(reconnect['sessions']) == 2 and all(
          any(m['target_system'] == 1 and m['target_component'] == 1 for m in session['requests']) and
          any(m['source_system'] == 1 and m['source_component'] == 1 and m['param_value'] == 0
              for m in session['values']) for session in reconnect['sessions']),
      'Controlled local relay reset and explicit reopen; no automatic reconnect or GUI claim.')
for command_case, expected_confirmations, expected_drops, expected_forwarded in (
        ('normal', [0], 0, 1), ('drop_one', [0, 1], 1, 1), ('drop_all', [0, 1, 2, 3], 4, 0)):
    command_dir = root / 'sitl-evidence' / ('command-ack-' + command_case)
    command_summary = json.loads((command_dir / 'summary.json').read_text())
    command_relay = json.loads((command_dir / 'relay-result.json').read_text())
    command_log = (command_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
    check('SITL command acknowledgement ' + command_case,
          command_summary['relay'] == command_relay and command_relay['errors'] == [] and
          command_relay['closed_by'] == 'client' and command_relay['buffered_bytes_at_close'] == 0 and
          command_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((command_dir / name).read_bytes()).hexdigest() == digest
              for name, digest in command_relay['capture_sha256'].items()) and
          [m['confirmation'] for m in command_summary['requests']] == expected_confirmations and
          all(m['target_system'] == 1 and m['target_component'] == 1 and m['param1'] == 30
              for m in command_summary['requests']) and
          len(command_summary['dropped_acks']) == expected_drops and
          len(command_summary['forwarded_acks']) == expected_forwarded and
          len(command_summary['received_acks']) == len(expected_confirmations) and
          all(m['source_system'] == 1 and m['source_component'] == 1 and m['result'] == 0
              for m in command_summary['received_acks']) and
          all(line in command_log for line in command_summary['verified_probe_lines']),
          'Read-only command through local ACK-loss relay; not evidence for side-effecting commands or UI.')
for command_case, expected_requests, expected_drops, expected_forwarded in (
        ('normal', 1, 0, 1), ('drop_one', 2, 1, 1), ('drop_all', 4, 4, 0)):
    command_dir = root / 'sitl-evidence' / ('command-int-ack-' + command_case)
    command_summary = json.loads((command_dir / 'summary.json').read_text())
    command_relay = json.loads((command_dir / 'relay-result.json').read_text())
    command_log = (command_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
    check('SITL command int acknowledgement ' + command_case,
          command_summary['relay'] == command_relay and command_relay['errors'] == [] and
          command_relay['closed_by'] == 'client' and command_relay['buffered_bytes_at_close'] == 0 and
          command_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((command_dir / name).read_bytes()).hexdigest() == digest
              for name, digest in command_relay['capture_sha256'].items()) and
          len(command_summary['requests']) == expected_requests and
          all(m['target_system'] == 1 and m['target_component'] == 1 and m['param1'] == 30 and
              m['frame'] == 0 and m['x'] == 0 and m['y'] == 0 for m in command_summary['requests']) and
          len(command_summary['dropped_acks']) == expected_drops and
          len(command_summary['forwarded_acks']) == expected_forwarded and
          len(command_summary['received_acks']) == expected_requests and
          all(m['source_system'] == 1 and m['source_component'] == 1 and m['result'] == 0
              for m in command_summary['received_acks']) and
          all(line in command_log for line in command_summary['verified_probe_lines']),
          'Read-only COMMAND_INT through local ACK-loss relay; no side-effect or UI claim.')
unsupported_dir = root / 'sitl-evidence/command-unsupported-normal'
unsupported = json.loads((unsupported_dir / 'summary.json').read_text())
unsupported_relay = json.loads((unsupported_dir / 'relay-result.json').read_text())
unsupported_log = (unsupported_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
check('SITL unsupported command responses', unsupported['relay'] == unsupported_relay and
      unsupported_relay['errors'] == [] and unsupported_relay['closed_by'] == 'client' and
      unsupported_relay['dropped_acks'] == 0 and unsupported_relay['buffered_bytes_at_close'] == 0 and
      unsupported_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((unsupported_dir / name).read_bytes()).hexdigest() == digest
          for name, digest in unsupported_relay['capture_sha256'].items()) and
      [m['mavpackettype'] for m in unsupported['requests']] == ['COMMAND_LONG', 'COMMAND_INT'] and
      all(m['command'] == 65530 and m['target_system'] == 1 and m['target_component'] == 1 for m in unsupported['requests']) and
      len(unsupported['acks']) == 2 and all(m['command'] == 65530 and m['result'] == 3 and
          m['source_system'] == 1 and m['source_component'] == 1 for m in unsupported['acks']) and
      all(line in unsupported_log for line in unsupported['verified_probe_lines']) and
      'scope describes interval request' in unsupported['relay_scope_correction'],
      'One unsupported ID against disposable SITL; relay scope label corrected in summary.')
synthetic_dir = root / 'sitl-evidence/command-ack-synthetic'
synthetic = json.loads((synthetic_dir / 'summary.json').read_text())
synthetic_log = (synthetic_dir / 'probe.log').read_text(encoding='utf-16')
synthetic_expected = {
    'wrong-system': ([[2, 1, 510, 0], [1, 1, 510, 2]], False, 0),
    'wrong-component': ([[1, 2, 510, 0], [1, 1, 510, 2]], False, 0),
    'wrong-command': ([[1, 1, 511, 0], [1, 1, 510, 2]], False, 0),
    'in-progress': ([[1, 1, 510, 5], [1, 1, 510, 0]], True, 0),
    'denied': ([[1, 1, 510, 2]], False, 0),
    'no-ack': ([[1, 1, 510, 2]], True, 11)}
check('synthetic command acknowledgement filtering', set(synthetic['cases']) == set(synthetic_expected) and
      all(hashlib.sha256((synthetic_dir / (name + '.bin')).read_bytes()).hexdigest() == synthetic['fixtures'][name]['sha256'] and
          synthetic['cases'][name]['frames'] == frames and synthetic['cases'][name]['result'] == answer and
          synthetic['cases'][name]['remaining'] == remaining and synthetic['cases'][name]['probe_line'] in synthetic_log
          for name, (frames, answer, remaining) in synthetic_expected.items()),
      'Synthetic in-memory MAVLink 1 ACKs; no vehicle, socket or full UI.')
synthetic_int = json.loads((synthetic_dir / 'summary-int.json').read_text())
synthetic_int_log = (synthetic_dir / 'probe-int.log').read_text(encoding='utf-16')
check('synthetic command int acknowledgement filtering',
      synthetic_int['fixtures'] == synthetic['fixtures'] and set(synthetic_int['cases']) == set(synthetic_expected) and
      all(synthetic_int['cases'][name]['frames'] == frames and
          synthetic_int['cases'][name]['result'] == (name == 'no-ack') and
          synthetic_int['cases'][name]['remaining'] == (11 if name in ('no-ack', 'in-progress') else 0) and
          synthetic_int['cases'][name]['probe_line'] in synthetic_int_log
          for name, (frames, _, _) in synthetic_expected.items()),
      'Synthetic COMMAND_INT ACKs; no vehicle or UI behavior claim.')
command_map = json.loads((root / 'mission-planner-binary-evidence/command-method-map.json').read_text())
command_index = root / 'mission-planner-binary-evidence/rea-supporting-index.sqlite'
with sqlite3.connect(f'file:{command_index.as_posix()}?mode=ro', uri=True) as connection:
    command_rows = {row[0]: row[1:] for row in connection.execute(
        'SELECT token,declaring_type,name,il_sha256,body_status FROM methods WHERE assembly=?',
        ('MissionPlanner.ArduPilot.dll',))}
    command_calls = {m['token']: [dict(zip(('il_offset', 'opcode', 'name', 'type'), row)) for row in connection.execute(
        'SELECT il_offset,opcode,target_name,target_declaring_type FROM calls WHERE assembly=? AND caller_token=? ORDER BY il_offset',
        ('MissionPlanner.ArduPilot.dll', m['token']))] for m in command_map['methods']}
check('REA command entry points and state machines',
      command_map['assembly_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      command_map['index_sha256'] == hashlib.sha256(command_index.read_bytes()).hexdigest() and
      [m['token'] for m in command_map['methods']] == ['0x06000460', '0x06000461', '0x06000462', '0x06000463',
                                                      '0x06000464', '0x060007f2', '0x060007f4'] and
      all(command_rows[m['token']] == (m['declaring_type'], m['name'], m['il_sha256'], m['body_status']) and
          command_calls[m['token']] == m['calls']
          for m in command_map['methods']),
      'Build-local REA method records; static references do not prove runtime dispatch.')
target_dir = root / 'sitl-evidence/command-ack-target-synthetic'
target_summary = json.loads((target_dir / 'summary.json').read_text())
target_log = (target_dir / 'probe.log').read_text(encoding='utf-16')
target_expected = {'wrong-target-then-denied': ([[1, 1, 510, 0, 42, 17], [1, 1, 510, 2, 255, 190]], True, 22),
                   'matching-denied': ([[1, 1, 510, 2, 255, 190]], False, 0),
                   'broadcast-accepted': ([[1, 1, 510, 0, 0, 0]], True, 0)}
check('synthetic MAVLink 2 ACK target fields', set(target_summary['cases']) == set(target_expected) and
      all(hashlib.sha256((target_dir / (name + '.bin')).read_bytes()).hexdigest() == target_summary['fixtures'][name]['sha256'] and
          target_summary['cases'][name]['frames'] == frames and target_summary['cases'][name]['result'] == answer and
          target_summary['cases'][name]['remaining'] == remaining and
          target_summary['cases'][name]['lines'] == [
              'FORM=%s CASE=%s RESULT=%s REMAINING=%d GIVE=False' % (form, name, str(answer), remaining)
              for form in ('long', 'int')] and
          all(line in target_log for line in target_summary['cases'][name]['lines'])
          for name, (frames, answer, remaining) in target_expected.items()),
      'Synthetic unsigned ACKs; no live link, security or UI impact established.')
for target_form in ('long', 'int'):
    live_dir = root / 'sitl-evidence' / ('command-target-live-' + target_form)
    live_summary = json.loads((live_dir / 'summary.json').read_text())
    live_relay = json.loads((live_dir / 'relay-result.json').read_text())
    live_log = (live_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
    live_original = (live_dir / 'original_ack.bin').read_bytes()
    live_modified = (live_dir / 'modified_ack.bin').read_bytes()
    check('SITL retargeted acknowledgement ' + target_form,
          live_summary['relay'] == live_relay and live_relay['case'] == 'retarget' and
          live_relay['errors'] == [] and live_relay['retargeted_acks'] == 1 and live_relay['closed_by'] == 'client' and
          live_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((live_dir / name).read_bytes()).hexdigest() == digest
              for name, digest in live_relay['capture_sha256'].items()) and
          live_original in (live_dir / 'to_client_input.bin').read_bytes() and
          live_modified in (live_dir / 'to_client_output.bin').read_bytes() and
          live_summary['byte_differences'] == [18, 19, 20, 21] and
          [i for i, (a, b) in enumerate(zip(live_original, live_modified)) if a != b] == [18, 19, 20, 21] and
          live_summary['original']['target'] == [255, 190] and live_summary['modified']['target'] == [42, 17] and
          live_summary['original']['source'] == live_summary['modified']['source'] == [1, 1] and
          live_summary['original']['command'] == live_summary['modified']['command'] == 510 and
          live_summary['original']['result'] == live_summary['modified']['result'] == 0 and
          live_summary['requests'] == [{'type': 'COMMAND_LONG' if target_form == 'long' else 'COMMAND_INT',
                                        'source': [255, 190], 'target': [1, 1], 'param1': 30.0}] and
          all(line in live_log for line in live_summary['verified_probe_lines']),
          'Controlled relay rewrites an unsigned ACK and checksum; not a signed-link or attack demonstration.')
for progress_form in ('long', 'int'):
    live_dir = root / 'sitl-evidence' / ('command-progress-live-' + progress_form)
    live_summary = json.loads((live_dir / 'summary.json').read_text())
    live_relay = json.loads((live_dir / 'relay-result.json').read_text())
    live_log = (live_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
    live_original = (live_dir / 'original_ack.bin').read_bytes()
    live_injected = (live_dir / 'injected_ack.bin').read_bytes()
    check('SITL injected progress acknowledgement ' + progress_form,
          live_summary['relay'] == live_relay and live_relay['case'] == 'inject_progress' and
          live_relay['errors'] == [] and live_relay['injected_acks'] == 1 and live_relay['closed_by'] == 'client' and
          live_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((live_dir / name).read_bytes()).hexdigest() == digest
              for name, digest in live_relay['capture_sha256'].items()) and
          live_original in (live_dir / 'to_client_input.bin').read_bytes() and
          live_injected + live_original in (live_dir / 'to_client_output.bin').read_bytes() and
          live_summary['byte_differences'] == [12, 20, 21] and
          [i for i, (a, b) in enumerate(zip(live_original, live_injected)) if a != b] == [12, 20, 21] and
          live_summary['original']['target'] == live_summary['injected']['target'] == [255, 190] and
          live_summary['original']['seq'] == live_summary['injected']['seq'] and
          live_summary['original']['result'] == 0 and live_summary['injected']['result'] == 5 and
          live_summary['requests'] == [{'type': 'COMMAND_LONG' if progress_form == 'long' else 'COMMAND_INT',
                                        'source': [255, 190], 'target': [1, 1], 'param1': 30.0}] and
          all(line in live_log for line in live_summary['verified_probe_lines']),
          'Synthetic progress ACK inserted with same sequence as original; no signed-link or UI claim.')
for progress_form in ('long', 'int'):
    seq_dir = root / 'sitl-evidence' / ('command-progress-sequential-' + progress_form)
    seq_summary = json.loads((seq_dir / 'summary.json').read_text())
    seq_relay = json.loads((seq_dir / 'relay-result.json').read_text())
    seq_log = (seq_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
    seq_original = (seq_dir / 'original_ack.bin').read_bytes()
    seq_injected = (seq_dir / 'injected_ack.bin').read_bytes()
    seq_shifted = (seq_dir / 'modified_ack.bin').read_bytes()
    check('SITL consecutive progress acknowledgement ' + progress_form,
          seq_summary['relay'] == seq_relay and seq_relay['case'] == 'inject_progress_sequential' and
          seq_relay['errors'] == [] and seq_relay['injected_acks'] == seq_relay['shifted_acks'] == 1 and
          seq_relay['closed_by'] == 'client' and
          seq_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((seq_dir / name).read_bytes()).hexdigest() == digest for name, digest in seq_relay['capture_sha256'].items()) and
          seq_original in (seq_dir / 'to_client_input.bin').read_bytes() and
          seq_injected + seq_shifted in (seq_dir / 'to_client_output.bin').read_bytes() and
          [i for i, (a, b) in enumerate(zip(seq_original, seq_injected)) if a != b] == seq_summary['progress_differences'] == [12, 20, 21] and
          [i for i, (a, b) in enumerate(zip(seq_original, seq_shifted)) if a != b] == seq_summary['shifted_differences'] == [4, 20, 21] and
          seq_summary['progress_seq'] == seq_summary['original_seq'] and
          seq_summary['shifted_seq'] == (seq_summary['original_seq'] + 1) % 256 and
          (seq_summary['original_result'], seq_summary['progress_result'], seq_summary['shifted_result']) == (0, 5, 0) and
          seq_summary['requests'] == [{'type': 'COMMAND_LONG' if progress_form == 'long' else 'COMMAND_INT',
                                       'source': [255, 190], 'target': [1, 1], 'param1': 30.0}] and
          all(line in seq_log for line in seq_summary['verified_probe_lines']),
          'Synthetic unsigned progress ACK and shifted final sequence; later stream not renumbered.')
drain_dir = root / 'sitl-evidence/command-progress-drain-int'
drain_summary = json.loads((drain_dir / 'summary.json').read_text())
drain_relay = json.loads((drain_dir / 'relay-result.json').read_text())
drain_log = (drain_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
drain_bytes = (drain_dir / 'drain.bin').read_bytes()
drain_original = (drain_dir / 'original_ack.bin').read_bytes()
drain_injected = (drain_dir / 'injected_ack.bin').read_bytes()
drain_accepted = (drain_dir / 'modified_ack.bin').read_bytes()
check('SITL progress acknowledgement post-return drain',
      drain_summary['relay'] == drain_relay and drain_relay['case'] == 'inject_progress_drain' and
      drain_relay['errors'] == [] and drain_relay['closed_by'] == 'client' and
      drain_relay['injected_acks'] == drain_relay['shifted_acks'] == 1 and
      drain_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((drain_dir / name).read_bytes()).hexdigest() == digest for name, digest in drain_relay['capture_sha256'].items()) and
      hashlib.sha256(drain_bytes).hexdigest() == drain_summary['drain_sha256'] and
      len(drain_bytes) == drain_summary['drain_bytes'] and drain_accepted in drain_bytes and
      drain_original in (drain_dir / 'to_client_input.bin').read_bytes() and
      drain_injected + drain_accepted in (drain_dir / 'to_client_output.bin').read_bytes() and
      len(drain_summary['decoded_acks']) == 1 and drain_summary['decoded_acks'][0]['result'] == 0 and
      drain_summary['decoded_acks'][0]['source'] == [1, 1] and drain_summary['decoded_acks'][0]['target'] == [255, 190] and
      drain_summary['decoded_acks'][0]['raw_sha256'] == hashlib.sha256(drain_accepted).hexdigest() and
      all(line in drain_log for line in drain_summary['verified_probe_lines']),
      'One synthetic progress injection; harness drains TCP after return, without full application reader.')
stale_dir = root / 'sitl-evidence/command-stale-ack-int'
stale = json.loads((stale_dir / 'summary.json').read_text())
stale_relay = json.loads((stale_dir / 'relay-result.json').read_text())
stale_log = (stale_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
check('SITL stale acknowledgement consumed by later command',
      stale['relay'] == stale_relay and stale_relay['case'] == 'stale_ack_test' and stale_relay['errors'] == [] and
      stale_relay['closed_by'] == 'client' and stale_relay['injected_acks'] == stale_relay['shifted_acks'] == stale_relay['dropped_acks'] == 1 and
      stale_relay['command_events'] == ['request1', 'first_progress_and_accepted_forwarded', 'request2', 'second_ack_dropped'] and
      stale_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((stale_dir / name).read_bytes()).hexdigest() == digest for name, digest in stale_relay['capture_sha256'].items()) and
      len(stale['requests']) == 2 and all(m['mavpackettype'] == 'COMMAND_INT' and m['command'] == 510 and
          m['target_system'] == 1 and m['target_component'] == 1 and m['param1'] == 30 for m in stale['requests']) and
      len(stale['simulator_acks']) == 2 and [m['result'] for m in stale['simulator_acks']] == [0, 0] and
      [m['result'] for m in stale['forwarded_acks']] == [5, 0] and len(stale['dropped_acks']) == 1 and
      stale['dropped_acks'][0]['raw_sha256'] == stale['simulator_acks'][1]['raw_sha256'] and
      all(line in stale_log for line in stale['verified_probe_lines']),
      'Controlled relay, two identical read-only commands; no full application or aircraft impact established.')
progress_dir = root / 'sitl-evidence/command-progress-only'
progress = json.loads((progress_dir / 'summary.json').read_text())
progress_fixture = json.loads((progress_dir / 'fixture.json').read_text())
progress_log = (progress_dir / 'probe.log').read_text(encoding='utf-16')
progress_bytes = (progress_dir / 'in-progress-only.bin').read_bytes()
progress_source = (synthetic_dir / 'in-progress.bin').read_bytes()
check('synthetic progress without terminal acknowledgement',
      progress['fixture'] == progress_fixture and progress['decoded_ack'] == [1, 1, 510, 5] and
      hashlib.sha256(progress_source).hexdigest() == progress_fixture['source_sha256'] and
      hashlib.sha256(progress_bytes).hexdigest() == progress_fixture['sha256'] and progress_bytes == progress_source[:11] and
      all(progress['observed'][form]['line'] in progress_log for form in ('long', 'int')) and
      'TIMEOUT=Timeout on read - doCommand' in progress['observed']['long']['line'] and
      'RESULT=False' in progress['observed']['int']['line'],
      'Single in-memory synthetic progress ACK; timing is one observation, not a guarantee.')
for mode_case, command_drop, legacy_drop, final_mode in (
        ('normal', 0, 0, 4), ('drop_cmd', 1, 0, 4), ('drop_legacy', 0, 2, 4), ('drop_all', 1, 2, 0)):
    mode_dir = root / 'sitl-evidence' / ('flight-mode-' + mode_case)
    mode_summary = json.loads((mode_dir / 'summary.json').read_text())
    mode_relay = json.loads((mode_dir / 'relay-result.json').read_text())
    mode_log = (mode_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
    check('SITL flight mode packet delivery ' + mode_case,
          mode_summary['relay'] == mode_relay and mode_relay['case'] == 'mode_' + mode_case and
          mode_relay['errors'] == [] and mode_relay['closed_by'] == 'client' and mode_relay['buffered_bytes_at_close'] == 0 and
          mode_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((mode_dir / name).read_bytes()).hexdigest() == digest for name, digest in mode_relay['capture_sha256'].items()) and
          mode_relay['mode_packets'] == {'command_seen': 1, 'command_dropped': command_drop,
                                         'legacy_seen': 2, 'legacy_dropped': legacy_drop} and
          [m['mavpackettype'] for m in mode_summary['sent']] == ['COMMAND_LONG', 'SET_MODE', 'SET_MODE'] and
          len(mode_summary['delivered']) == 3 - command_drop - legacy_drop and len(mode_summary['dropped']) == command_drop + legacy_drop and
          mode_summary['final_observed_mode'] == final_mode and
          all((m['base_mode'] & 128) == 0 for m in mode_summary['heartbeats']) and
          any(m['custom_mode'] == final_mode for m in mode_summary['heartbeats']) and
          all(line in mode_log for line in mode_summary['verified_probe_lines']),
          'One disarmed mode transition with controlled packet loss; not full UI or flight behavior.')
invalid_mode_dir = root / 'sitl-evidence/flight-mode-invalid'
invalid_mode = json.loads((invalid_mode_dir / 'summary.json').read_text())
invalid_relay = json.loads((invalid_mode_dir / 'relay-result.json').read_text())
invalid_log = (invalid_mode_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
check('SITL rejected numeric flight mode', invalid_mode['relay'] == invalid_relay and
      invalid_relay['case'] == 'mode_invalid' and invalid_relay['errors'] == [] and invalid_relay['closed_by'] == 'client' and
      invalid_relay['mode_packets'] == {'command_seen': 1, 'command_dropped': 0, 'legacy_seen': 2, 'legacy_dropped': 0} and
      invalid_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((invalid_mode_dir / name).read_bytes()).hexdigest() == digest for name, digest in invalid_relay['capture_sha256'].items()) and
      [m['mavpackettype'] for m in invalid_mode['sent']] == ['COMMAND_LONG', 'SET_MODE', 'SET_MODE'] and
      invalid_mode['sent'][0]['param1'] == 1 and invalid_mode['sent'][0]['param2'] == 999 and
      all(m['base_mode'] == 1 and m['custom_mode'] == 999 for m in invalid_mode['sent'][1:]) and
      bool(invalid_mode['acks']) and all(m['command'] == 176 and m['result'] == 4 and m['source'] == [1, 1] for m in invalid_mode['acks']) and
      bool(invalid_mode['heartbeats']) and all(m['custom_mode'] == 0 and (m['base_mode'] & 128) == 0 for m in invalid_mode['heartbeats']) and
      all(line in invalid_log for line in invalid_mode['verified_probe_lines']),
      'Invalid numeric mode in disarmed SITL; no UI or aircraft behavior claim.')
for string_case in ('string', 'string_verified'):
    string_dir = root / 'sitl-evidence' / ('flight-mode-' + string_case)
    string_summary = json.loads((string_dir / 'summary.json').read_text())
    string_relay = json.loads((string_dir / 'relay-result.json').read_text())
    string_log = (string_dir / 'probe.log').read_text(encoding='utf-16', errors='replace')
    string_hashes = string_summary['library_hashes']
    check('SITL Copter string mode ' + string_case,
          string_summary['relay'] == string_relay and string_relay['case'] == 'mode_' + string_case and
          string_relay['errors'] == [] and string_relay['closed_by'] == 'client' and
          string_relay['mode_packets'] == {'command_seen': 1, 'command_dropped': 0, 'legacy_seen': 2, 'legacy_dropped': 0} and
          string_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((string_dir / name).read_bytes()).hexdigest() == digest for name, digest in string_relay['capture_sha256'].items()) and
          hashlib.sha256((string_dir / 'ArduCopter.apm.pdef.xml').read_bytes()).hexdigest() == string_summary['metadata_sha256'] and
          string_summary['metadata_guided_option'].lower() == 'guided' and
          string_hashes['original_ardupilot'] == string_hashes['test_ardupilot'] ==
          hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
          string_hashes['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
          string_hashes['original_utilities'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
          string_hashes['test_utilities'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
          string_hashes['original_utilities'] != string_hashes['test_utilities'] and
          [m['mavpackettype'] for m in string_summary['sent']] == ['COMMAND_LONG', 'SET_MODE', 'SET_MODE'] and
          string_summary['sent'][0]['param1'] == 1 and string_summary['sent'][0]['param2'] == 4 and
          all(m['base_mode'] == 1 and m['custom_mode'] == 4 for m in string_summary['sent'][1:]) and
          any(m['custom_mode'] == 0 for m in string_summary['heartbeats']) and
          any(m['custom_mode'] == 4 for m in string_summary['heartbeats']) and
          all((m['base_mode'] & 128) == 0 for m in string_summary['heartbeats']) and
          string_summary['metadata_reflection_checked'] == (string_case == 'string_verified') and
          (string_case != 'string_verified' or 'PDEF_LOADED=True XML_MATCH=True VALUES_NONEMPTY=True VALUES_MATCH=True' in string_log) and
          all(line in string_log for line in string_summary['verified_probe_lines']),
          'Original ArduPilot assembly, test-patched Utilities data directory, local metadata and disarmed SITL; no UI.')
invalid_string_dir = root / 'sitl-evidence/flight-mode-string_invalid'
invalid_string = json.loads((invalid_string_dir / 'summary.json').read_text())
invalid_string_relay = json.loads((invalid_string_dir / 'relay-result.json').read_text())
invalid_string_log = (invalid_string_dir / 'probe.log').read_text(encoding='utf-8')
invalid_string_hashes = invalid_string['library_hashes']
check('SITL rejected Copter mode name', invalid_string['relay'] == invalid_string_relay and
      invalid_string_relay['case'] == 'mode_string_invalid' and invalid_string_relay['errors'] == [] and
      invalid_string_relay['closed_by'] == 'client' and invalid_string_relay['buffered_bytes_at_close'] == 0 and
      invalid_string_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      invalid_string_relay['mode_packets'] == {'command_seen': 0, 'command_dropped': 0, 'legacy_seen': 0, 'legacy_dropped': 0} and
      all(hashlib.sha256((invalid_string_dir / name).read_bytes()).hexdigest() == digest for name, digest in invalid_string_relay['capture_sha256'].items()) and
      hashlib.sha256((invalid_string_dir / 'ArduCopter.apm.pdef.xml').read_bytes()).hexdigest() == invalid_string['metadata_sha256'] and
      invalid_string_hashes['original_ardupilot'] == invalid_string_hashes['test_ardupilot'] ==
      hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      invalid_string_hashes['original_utilities'] != invalid_string_hashes['test_utilities'] and
      invalid_string_hashes['original_utilities'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      invalid_string_hashes['test_utilities'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      invalid_string['sent'] == [] and bool(invalid_string['heartbeats']) and
      all(m['custom_mode'] == 0 and not (m['base_mode'] & 128) for m in invalid_string['heartbeats']) and
      all(line in invalid_string_log for line in invalid_string['verified_probe_lines']),
      'Invalid mode name, patched Utilities data directory and disarmed SITL; no UI or real vehicle.')
accel_dir = root / 'sitl-evidence/command-ack-calibration_start'
accel = json.loads((accel_dir / 'summary.json').read_text())
accel_relay = json.loads((accel_dir / 'relay-result.json').read_text())
accel_log = (accel_dir / 'probe.log').read_text(encoding='utf-8')
check('SITL accelerometer calibration start', accel['relay'] == accel_relay and
      accel_relay['case'] == 'calibration_start' and accel_relay['errors'] == [] and
      accel_relay['closed_by'] == 'client' and accel_relay['buffered_bytes_at_close'] == 0 and
      accel_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((accel_dir / name).read_bytes()).hexdigest() == digest for name, digest in accel_relay['capture_sha256'].items()) and
      accel['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      len(accel['start']) == 1 and accel['start'][0]['command'] == 241 and accel['start'][0]['param5'] == 1 and
      bool(accel['acknowledgements']) and all(m['command'] == 241 and m['result'] == 0 for m in accel['acknowledgements']) and
      len(accel['position_requests']) >= 2 and all(m['command'] == 42429 and m['param1'] == 1 for m in accel['position_requests']) and
      bool(accel['heartbeats']) and all(not (m['base_mode'] & 128) for m in accel['heartbeats']) and
      all(line in accel_log for line in accel['verified_probe_lines']),
      'Disarmed SITL calibration start only; no position confirmed, calibration completion or UI.')
accel_step_dir = root / 'sitl-evidence/command-ack-calibration_step'
accel_step = json.loads((accel_step_dir / 'summary.json').read_text())
accel_step_relay = json.loads((accel_step_dir / 'relay-result.json').read_text())
accel_step_log = (accel_step_dir / 'probe.log').read_text(encoding='utf-8')
check('SITL accelerometer calibration first position', accel_step['relay'] == accel_step_relay and
      accel_step_relay['case'] == 'calibration_step' and accel_step_relay['errors'] == [] and
      accel_step_relay['closed_by'] == 'client' and accel_step_relay['buffered_bytes_at_close'] == 0 and
      accel_step_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((accel_step_dir / name).read_bytes()).hexdigest() == digest for name, digest in accel_step_relay['capture_sha256'].items()) and
      accel_step['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      [m['param1'] for m in accel_step['position_responses']] == [2, 1] and
      all(m['target_system'] == 0 and m['target_component'] == 0 for m in accel_step['position_responses']) and
      [(m['mavpackettype'], m.get('param1'), m.get('result')) for m in accel_step['position_events']] == [
          ('COMMAND_LONG', 1, None), ('COMMAND_ACK', None, 4), ('COMMAND_LONG', 1, None),
          ('COMMAND_LONG', 1, None), ('COMMAND_LONG', 1, None), ('COMMAND_ACK', None, 0), ('COMMAND_LONG', 2, None)] and
      bool(accel_step['heartbeats']) and all(not (m['base_mode'] & 128) for m in accel_step['heartbeats']) and
      all(line in accel_step_log for line in accel_step['verified_probe_lines']) and
      [accel_step_log.index(line) for line in accel_step['verified_probe_lines']] == sorted(accel_step_log.index(line) for line in accel_step['verified_probe_lines']),
      'Disarmed SITL, first position only; broadcast target fields observed; no UI or completed calibration.')
accel_full_dir = root / 'sitl-evidence/command-ack-calibration_full'
accel_full = json.loads((accel_full_dir / 'summary.json').read_text())
accel_full_relay = json.loads((accel_full_dir / 'relay-result.json').read_text())
accel_full_log = (accel_full_dir / 'probe.log').read_text(encoding='utf-8')
check('SITL six-position accelerometer calibration', accel_full['relay'] == accel_full_relay and
      accel_full_relay['case'] == 'calibration_full' and accel_full_relay['errors'] == [] and
      accel_full_relay['closed_by'] == 'client' and accel_full_relay['buffered_bytes_at_close'] == 0 and
      accel_full_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((accel_full_dir / name).read_bytes()).hexdigest() == digest for name, digest in accel_full_relay['capture_sha256'].items()) and
      accel_full['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      accel_full['relay_source_sha256'] == hashlib.sha256((accel_full_dir / 'relay-source.py').read_bytes()).hexdigest() and
      accel_full['probe_source_sha256'] == hashlib.sha256((accel_full_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      "'calibration' if case == 'calibration_full' else 'quad'" in (accel_full_dir / 'relay-source.py').read_text(encoding='utf-8') and
      len(accel_full['start']) == 1 and accel_full['start'][0]['param5'] == 1 and
      len(accel_full['start_acks']) == 1 and accel_full['start_acks'][0]['result'] == 0 and
      [m['param1'] for m in accel_full['position_responses']] == list(range(1, 7)) and
      all(m['target_system'] == 0 and m['target_component'] == 0 for m in accel_full['position_responses']) and
      len([m for m in accel_full['position_events'] if m['mavpackettype'] == 'COMMAND_ACK' and m['result'] == 0]) == 6 and
      len(accel_full['servo_commands']) == len(accel_full['servo_acks']) == 22 and all(m['result'] == 0 for m in accel_full['servo_acks']) and
      bool(accel_full['success_messages']) and all('Calibration successful' in m['text'] for m in accel_full['success_messages']) and
      bool(accel_full['heartbeats']) and all(not (m['base_mode'] & 128) for m in accel_full['heartbeats']) and
      all(line in accel_full_log for line in accel_full['verified_probe_lines']) and
      [accel_full_log.index(line) for line in accel_full['verified_probe_lines']] == sorted(accel_full_log.index(line) for line in accel_full['verified_probe_lines']),
      'Disarmed SITL calibration model and original library; no physical sensors or UI; no post-reboot persistence claim.')
accel_reboot_dir = root / 'sitl-evidence/accel-calibration-reboot'
accel_reboot = json.loads((accel_reboot_dir / 'summary.json').read_text())
accel_reboot_result = json.loads((accel_reboot_dir / 'result.json').read_text())
check('SITL accelerometer calibration reboot readback', accel_reboot_result['errors'] == [] and
      accel_reboot['binary_sha256'] == accel_reboot_result['binary_sha256'] ==
      hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      accel_reboot['source_capture_sha256'] == accel_reboot_result['original_capture_sha256'] ==
      hashlib.sha256((accel_full_dir / 'to_client_output.bin').read_bytes()).hexdigest() and
      accel_reboot['readback_capture_sha256'] == accel_reboot_result['downlink_sha256'] ==
      hashlib.sha256((accel_reboot_dir / 'downlink.bin').read_bytes()).hexdigest() and
      accel_reboot['original_storage_sha256'] == accel_reboot_result['source_storage_sha256'] == accel_reboot_result['copied_storage_sha256'] ==
      hashlib.sha256((accel_reboot_dir / 'eeprom-before.bin').read_bytes()).hexdigest() ==
      hashlib.sha256((accel_full_dir / 'eeprom.bin').read_bytes()).hexdigest() and
      accel_reboot['reboot_storage_after_shutdown_sha256'] == accel_reboot_result['post_shutdown_storage_sha256'] ==
      hashlib.sha256((accel_reboot_dir / 'eeprom.bin').read_bytes()).hexdigest() and
      accel_reboot['readback_source_sha256'] == hashlib.sha256((accel_reboot_dir / 'readback-source.py').read_bytes()).hexdigest() and
      len(accel_reboot['parameter_values']) == 14 and accel_reboot['parameter_values'] ==
      accel_reboot_result['expected_from_prior_capture'] == accel_reboot_result['observed_after_reboot'] and
      accel_reboot['heartbeat_count'] > 0 and not (accel_reboot_result['initial_heartbeat']['base_mode'] & 128),
      'Fourteen simulator calibration values after one restart from copied storage; no physical hardware or UI.')
for armed_case in ('calibration_armed', 'calibration_armed_observed'):
    armed_dir = root / 'sitl-evidence' / ('command-ack-' + armed_case)
    armed_summary = json.loads((armed_dir / 'summary.json').read_text())
    armed_relay = json.loads((armed_dir / 'relay-result.json').read_text())
    armed_log = (armed_dir / 'probe.log').read_text(encoding='utf-8')
    check('SITL armed calibration rejection ' + armed_case, armed_summary['relay'] == armed_relay and
          armed_relay['case'] == armed_case and armed_relay['errors'] == [] and armed_relay['closed_by'] == 'client' and
          armed_relay['buffered_bytes_at_close'] == 0 and
          armed_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((armed_dir / name).read_bytes()).hexdigest() == digest for name, digest in armed_relay['capture_sha256'].items()) and
          armed_summary['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
          [m['param1'] for m in armed_summary['arm_commands']] == ([1] if armed_case == 'calibration_armed' else [1, 0]) and
          all(m['param2'] == 21196 for m in armed_summary['arm_commands']) and
          len(armed_summary['calibration_commands']) == 1 and armed_summary['calibration_commands'][0]['param5'] == 1 and
          len(armed_summary['calibration_ack']) == 1 and armed_summary['calibration_ack'][0]['result'] == 4 and
          bool(armed_summary['notices']) and any(m['base_mode'] & 128 for m in armed_summary['heartbeats']) and
          (armed_case == 'calibration_armed' or not (armed_summary['heartbeats'][-1]['base_mode'] & 128)) and
          all(line in armed_log for line in armed_summary['verified_probe_lines']) and
          [armed_log.index(line) for line in armed_summary['verified_probe_lines']] == sorted(armed_log.index(line) for line in armed_summary['verified_probe_lines']),
          'Simulator only; full-calibration library call returns before failed ACK; full UI untested.')
for control_case in ('calibration_control', 'calibration_control_retry'):
    control_dir = root / 'sitl-evidence' / ('command-ack-' + control_case)
    control_summary = json.loads((control_dir / 'summary.json').read_text())
    control_relay = json.loads((control_dir / 'relay-result.json').read_text())
    control_log = (control_dir / 'probe.log').read_text(encoding='utf-8')
    control_hashes = control_summary['assembly_hashes']
    check('Instrumented armed calibration control ' + control_case,
          control_summary['relay'] == control_relay and control_relay['case'] == control_case and
          control_relay['errors'] == [] and control_relay['closed_by'] == 'client' and control_relay['buffered_bytes_at_close'] == 0 and
          control_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((control_dir / name).read_bytes()).hexdigest() == digest for name, digest in control_relay['capture_sha256'].items()) and
          control_summary['probe_source_sha256'] == hashlib.sha256((control_dir / 'probe-source.cs').read_bytes()).hexdigest() and
          control_summary['probe_exe_sha256'] == hashlib.sha256((control_dir / 'probe.exe').read_bytes()).hexdigest() and
          control_hashes['original_main'] == control_hashes['test_main'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.exe').read_bytes()).hexdigest() and
          control_hashes['test_main'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.exe').read_bytes()).hexdigest() and
          control_hashes['original_library'] == control_hashes['test_library'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
          control_hashes['test_library'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
          control_hashes['original_utilities'] != control_hashes['test_utilities'] and
          control_hashes['original_utilities'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
          control_hashes['test_utilities'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
          [m['command'] for m in control_summary['commands']] == ([241] if control_case == 'calibration_control' else [241, 42429]) and
          [m['command'] for m in control_summary['acks']] == [m['command'] for m in control_summary['commands']] and
          all(m['result'] == 4 for m in control_summary['acks']) and
          (control_case == 'calibration_control' or (control_summary['commands'][1]['param1'] == 0 and control_summary['commands'][1]['target_system'] == 0 and control_summary['commands'][1]['target_component'] == 0)) and
          bool(control_summary['notices']) and any(m['base_mode'] & 128 for m in control_summary['heartbeats']) and
          all(line in control_log for line in control_summary['verified_probe_lines']) and
          [control_log.index(line) for line in control_summary['verified_probe_lines']] == sorted(control_log.index(line) for line in control_summary['verified_probe_lines']),
          'Direct handler invocation on unrendered control, patched Utilities and simulator; no rendered-screen interaction claim.')
lifecycle_dir = root / 'sitl-evidence/command-ack-calibration_lifecycle_observed'
lifecycle = json.loads((lifecycle_dir / 'summary.json').read_text())
lifecycle_relay = json.loads((lifecycle_dir / 'relay-result.json').read_text())
lifecycle_log = (lifecycle_dir / 'probe.log').read_text(encoding='utf-8')
check('Instrumented calibration control lifecycle', lifecycle['relay'] == lifecycle_relay and
      lifecycle_relay['case'] == 'calibration_lifecycle_observed' and lifecycle_relay['errors'] == [] and
      lifecycle_relay['closed_by'] == 'client' and
      lifecycle_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((lifecycle_dir / name).read_bytes()).hexdigest() == digest for name, digest in lifecycle_relay['capture_sha256'].items()) and
      lifecycle['probe_source_sha256'] == hashlib.sha256((lifecycle_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      lifecycle['probe_exe_sha256'] == hashlib.sha256((lifecycle_dir / 'probe.exe').read_bytes()).hexdigest() and
      lifecycle['log_sha256'] == hashlib.sha256((lifecycle_dir / 'probe.log').read_bytes()).hexdigest() and
      lifecycle['main_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.exe').read_bytes()).hexdigest() and
      lifecycle['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      lifecycle['utilities_sha256'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      [(m['command'], m['param1']) for m in lifecycle['commands']] == [(400, 1), (241, 0), (241, 0), (400, 0)] and
      [(m['command'], m['result']) for m in lifecycle['acks']] == [(400, 0), (241, 4), (241, 4), (400, 0)] and
      lifecycle['probe_exit'] == 124 and (lifecycle_dir / 'probe-exit.txt').read_text().strip() == '124' and
      all(line in lifecycle_log for line in lifecycle['verified_probe_lines']) and
      [lifecycle_log.index(line) for line in lifecycle['verified_probe_lines']] == sorted(lifecycle_log.index(line) for line in lifecycle['verified_probe_lines']),
      'Unrendered instrumented control, simulator disarm ACK captured, harness timed out; cause not established.')
pumped_dir = root / 'sitl-evidence/command-ack-calibration_lifecycle_pumped'
pumped = json.loads((pumped_dir / 'summary.json').read_text())
pumped_relay = json.loads((pumped_dir / 'relay-result.json').read_text())
pumped_log = (pumped_dir / 'probe.log').read_text(encoding='utf-8')
check('Instrumented calibration control pumped lifecycle', pumped['relay'] == pumped_relay and
      pumped_relay['case'] == 'calibration_lifecycle_pumped' and pumped_relay['errors'] == [] and
      pumped_relay['closed_by'] == 'client' and pumped_relay['buffered_bytes_at_close'] == 0 and
      pumped_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((pumped_dir / name).read_bytes()).hexdigest() == digest for name, digest in pumped_relay['capture_sha256'].items()) and
      pumped['probe_source_sha256'] == hashlib.sha256((pumped_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      pumped['probe_exe_sha256'] == hashlib.sha256((pumped_dir / 'probe.exe').read_bytes()).hexdigest() and
      pumped['log_sha256'] == hashlib.sha256((pumped_dir / 'probe.log').read_bytes()).hexdigest() and
      pumped['main_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.exe').read_bytes()).hexdigest() and
      pumped['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      pumped['utilities_sha256'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      [(m['command'], m['param1']) for m in pumped['commands']] == [(400, 1), (241, 0), (241, 0), (400, 0)] and
      [(m['command'], m['result']) for m in pumped['acks']] == [(400, 0), (241, 4), (241, 4), (400, 0)] and
      pumped['probe_exit'] == 0 and (pumped_dir / 'probe-exit.txt').read_text().strip() == '0' and
      all(line in pumped_log for line in pumped['verified_probe_lines']) and
      [pumped_log.index(line) for line in pumped['verified_probe_lines']] == sorted(pumped_log.index(line) for line in pumped['verified_probe_lines']),
      'Unrendered control; worker disarm plus message pump; normal app behavior untested.')
page_dir = root / 'sitl-evidence/command-ack-calibration_page_navigation'
page_summary = json.loads((page_dir / 'summary.json').read_text())
page_relay = json.loads((page_dir / 'relay-result.json').read_text())
page_log = (page_dir / 'probe.log').read_text(encoding='utf-8')
check('Instrumented calibration backstage navigation', page_summary['relay'] == page_relay and
      page_relay['case'] == 'calibration_page_navigation' and page_relay['errors'] == [] and
      page_relay['closed_by'] == 'client' and page_relay['buffered_bytes_at_close'] == 0 and
      page_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((page_dir / name).read_bytes()).hexdigest() == digest for name, digest in page_relay['capture_sha256'].items()) and
      page_summary['probe_source_sha256'] == hashlib.sha256((page_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      page_summary['probe_exe_sha256'] == hashlib.sha256((page_dir / 'probe.exe').read_bytes()).hexdigest() and
      page_summary['log_sha256'] == hashlib.sha256((page_dir / 'probe.log').read_bytes()).hexdigest() and
      page_summary['main_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.exe').read_bytes()).hexdigest() and
      page_summary['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      page_summary['controls_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Controls.dll').read_bytes()).hexdigest() ==
      hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Controls.dll').read_bytes()).hexdigest() and
      page_summary['utilities_sha256'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      [(m['command'], m['param1']) for m in page_summary['commands']] == [(400, 1), (241, 0), (241, 0), (400, 0)] and
      [(m['command'], m['result']) for m in page_summary['acks']] == [(400, 0), (241, 4), (241, 4), (400, 0)] and
      page_summary['probe_exit'] == 0 and (page_dir / 'probe-exit.txt').read_text().strip() == '0' and
      'SAME_CONTROL=True' in page_log and all(line in page_log for line in page_summary['verified_probe_lines']) and
      [page_log.index(line) for line in page_summary['verified_probe_lines']] == sorted(page_log.index(line) for line in page_summary['verified_probe_lines']),
      'Unrendered BackstageView page switch; patched Utilities and simulator; no physical UI interaction.')
page_close_dir = root / 'sitl-evidence/command-ack-calibration_page_close_retry'
page_close = json.loads((page_close_dir / 'summary.json').read_text())
page_close_relay = json.loads((page_close_dir / 'relay-result.json').read_text())
page_close_log = (page_close_dir / 'probe.log').read_text(encoding='utf-8')
first_close_dir = root / 'sitl-evidence/command-ack-calibration_page_close'
first_close_log = (first_close_dir / 'probe.log').read_text(encoding='utf-8')
check('Instrumented calibration backstage disposal', page_close['relay'] == page_close_relay and
      page_close_relay['case'] == 'calibration_page_close_retry' and page_close_relay['errors'] == [] and
      page_close_relay['closed_by'] == 'client' and page_close_relay['buffered_bytes_at_close'] == 0 and
      page_close_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((page_close_dir / name).read_bytes()).hexdigest() == digest for name, digest in page_close_relay['capture_sha256'].items()) and
      page_close['probe_source_sha256'] == hashlib.sha256((page_close_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      page_close['probe_exe_sha256'] == hashlib.sha256((page_close_dir / 'probe.exe').read_bytes()).hexdigest() and
      page_close['log_sha256'] == hashlib.sha256((page_close_dir / 'probe.log').read_bytes()).hexdigest() and
      page_close['main_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.exe').read_bytes()).hexdigest() and
      page_close['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      page_close['controls_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Controls.dll').read_bytes()).hexdigest() ==
      hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Controls.dll').read_bytes()).hexdigest() and
      page_close['utilities_sha256'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      [(m['command'], m['param1']) for m in page_close['commands']] == [(400, 1), (241, 0), (241, 0), (400, 0)] and
      [(m['command'], m['result']) for m in page_close['acks']] == [(400, 0), (241, 4), (241, 4), (400, 0)] and
      page_close['probe_exit'] == 0 and (page_close_dir / 'probe-exit.txt').read_text().strip() == '0' and
      'AFTER_CLOSE_DISPOSED=True SUBSCRIPTIONS=4' in page_close_log and
      all(line in page_close_log for line in page_close['verified_probe_lines']) and
      [page_close_log.index(line) for line in page_close['verified_probe_lines']] == sorted(page_close_log.index(line) for line in page_close['verified_probe_lines']) and
      (first_close_dir / 'probe-exit.txt').read_text().strip() == '1' and 'System.Reflection.AmbiguousMatchException' in first_close_log,
      'Instrumented unrendered page disposal before link close; first reflection attempt failed and is retained.')
disposed_dir = root / 'sitl-evidence/command-ack-calibration_disposed_callback'
disposed = json.loads((disposed_dir / 'summary.json').read_text())
disposed_relay = json.loads((disposed_dir / 'relay-result.json').read_text())
disposed_log = (disposed_dir / 'probe.log').read_text(encoding='utf-8')
disposed_after = disposed_log[disposed_log.index('AFTER_CLOSE_DISPOSED=True SUBSCRIPTIONS=4'):]
check('Disposed calibration control callback exceptions', disposed['relay'] == disposed_relay and
      disposed_relay['case'] == 'calibration_disposed_callback' and disposed_relay['errors'] == [] and
      disposed_relay['closed_by'] == 'client' and disposed_relay['buffered_bytes_at_close'] == 0 and
      disposed_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((disposed_dir / name).read_bytes()).hexdigest() == digest for name, digest in disposed_relay['capture_sha256'].items()) and
      disposed['probe_source_sha256'] == hashlib.sha256((disposed_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      disposed['probe_exe_sha256'] == hashlib.sha256((disposed_dir / 'probe.exe').read_bytes()).hexdigest() and
      disposed['log_sha256'] == hashlib.sha256((disposed_dir / 'probe.log').read_bytes()).hexdigest() and
      disposed['main_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.exe').read_bytes()).hexdigest() and
      disposed['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      disposed['controls_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Controls.dll').read_bytes()).hexdigest() and
      disposed['utilities_sha256'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      [(m['command'], m['param1']) for m in disposed['commands']] == [(400, 1), (241, 0), (241, 0), (400, 0), (241, 0)] and
      [(m['command'], m['result']) for m in disposed['acks']] == [(400, 0), (241, 4), (241, 4), (400, 0), (241, 0)] and
      disposed['probe_exit'] == 0 and (disposed_dir / 'probe-exit.txt').read_text().strip() == '0' and
      disposed['disposed_callback_error_count'] >= 2 and disposed_after.count(disposed['disposed_callback_error']) == disposed['disposed_callback_error_count'] and
      all('ConfigAccelerometerCalibration.UpdateUserMessage' in part[:900] and 'MAVLinkInterface.PacketReceived' in part[:900]
          for part in disposed_after.split(disposed['disposed_callback_error'])[1:]) and
      all(line in disposed_log for line in disposed['verified_probe_lines']),
      'Unrendered disposed control and disposable SITL; caught callback exceptions logged; full app impact untested.')
backstage_map = json.loads((root / 'mission-planner-binary-evidence/backstage-page-method-map.json').read_text())
backstage_index = root / 'mission-planner-binary-evidence/rea-supporting-index.sqlite'
with sqlite3.connect(f'file:{backstage_index.as_posix()}?mode=ro', uri=True) as connection:
    backstage_rows = {m['token']: connection.execute('select declaring_type,name,il_sha256,body_status from methods where assembly=? and token=?',
        ('MissionPlanner.Controls.dll', m['token'])).fetchone() for m in backstage_map['methods']}
    backstage_calls = {m['token']: [dict(zip(('il_offset', 'opcode', 'name', 'type'), row)) for row in connection.execute(
        'select il_offset,opcode,target_name,target_declaring_type from calls where assembly=? and caller_token=? order by il_offset',
        ('MissionPlanner.Controls.dll', m['token']))] for m in backstage_map['methods']}
check('REA backstage page method records', backstage_map['assembly_sha256'] ==
      hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Controls.dll').read_bytes()).hexdigest() and
      backstage_map['index_sha256'] == hashlib.sha256(backstage_index.read_bytes()).hexdigest() and
      [m['token'] for m in backstage_map['methods']] == ['0x06000341', '0x06000364', '0x06000365'] and
      all(backstage_rows[m['token']] == (m['declaring_type'], m['name'], m['il_sha256'], m['body_status']) and
          backstage_calls[m['token']] == m['calls'] for m in backstage_map['methods']) and
      {'Activate', 'Deactivate'} <= {c['name'] for c in backstage_map['methods'][0]['calls']} and
      'CreateInstance' in {c['name'] for c in backstage_map['methods'][1]['calls']},
      'Static REA method and call references, not observed page navigation.')
terrain_fixture = root / 'sitl-evidence/terrain-fixture-data/S36E149.hgt'
terrain_bytes = terrain_fixture.read_bytes()
for terrain_case in ('terrain_fixture', 'terrain_fixture_stream'):
    terrain_dir = root / 'sitl-evidence' / ('command-ack-' + terrain_case)
    terrain = json.loads((terrain_dir / 'summary.json').read_text())
    terrain_relay = json.loads((terrain_dir / 'relay-result.json').read_text())
    terrain_log = (terrain_dir / 'probe.log').read_text(encoding='utf-8')
    terrain_hashes = terrain['library_hashes']
    check('SITL synthetic terrain ' + terrain_case, terrain['relay'] == terrain_relay and
          terrain_relay['case'] == terrain_case and terrain_relay['errors'] == [] and terrain_relay['closed_by'] == 'client' and
          terrain_relay['buffered_bytes_at_close'] == 0 and
          terrain_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((terrain_dir / name).read_bytes()).hexdigest() == digest for name, digest in terrain_relay['capture_sha256'].items()) and
          terrain['fixture_sha256'] == hashlib.sha256(terrain_bytes).hexdigest() and len(terrain_bytes) == 1201 * 1201 * 2 and
          terrain_bytes == (321).to_bytes(2, 'big', signed=True) * (1201 * 1201) and
          terrain['probe_source_sha256'] == hashlib.sha256((terrain_dir / 'probe-source.cs').read_bytes()).hexdigest() and
          terrain['probe_exe_sha256'] == hashlib.sha256((terrain_dir / 'probe.exe').read_bytes()).hexdigest() and
          terrain['probe_log_sha256'] == hashlib.sha256((terrain_dir / 'probe.log').read_bytes()).hexdigest() and
          terrain_hashes['original_ardupilot'] == terrain_hashes['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
          terrain_hashes['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
          terrain_hashes['original_mavlink'] == terrain_hashes['test_mavlink'] == hashlib.sha256((root / 'mission-planner-portable/MAVLink.dll').read_bytes()).hexdigest() and
          terrain_hashes['test_mavlink'] == hashlib.sha256((root / 'mission-planner-isolated/MAVLink.dll').read_bytes()).hexdigest() and
          terrain_hashes['original_utilities'] != terrain_hashes['test_utilities'] and
          terrain_hashes['original_utilities'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
          terrain_hashes['test_utilities'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
          bool(terrain['checks']) and all(m['lat'] == -353632610 and m['lon'] == 1491652300 for m in terrain['checks']) and
          bool(terrain['heartbeats']) and all(not (m['base_mode'] & 128) for m in terrain['heartbeats']) and
          all(line in terrain_log for line in terrain['verified_probe_lines']) and
          ((terrain_case == 'terrain_fixture' and (terrain_dir / 'probe-exit.txt').read_text().strip() == '1' and not terrain['requests'] and not terrain['data']) or
           (terrain_case == 'terrain_fixture_stream' and (terrain_dir / 'probe-exit.txt').read_text().strip() == '0' and len(terrain['data']) == 40 and
            any(m['req_stream_id'] == 0 and m['req_message_rate'] == 4 and m['start_stop'] == 1 for m in terrain['streams']) and
            all(len(m['data']) == 16 and all(v == 321 for v in m['data']) for m in terrain['data']) and
            all(any(m['lat'] == r['lat'] and m['lon'] == r['lon'] and m['grid_spacing'] == r['grid_spacing'] and (r['mask'] & (1 << m['gridbit']))
                    for r in terrain['requests']) for m in terrain['data']) and
            any(m['lat'] == -353632610 and m['lon'] == 1491652300 and m['terrain_height'] == 321 and m['pending'] == 16 and m['loaded'] == 40 for m in terrain['reports']))),
          'Synthetic flat tile, patched Utilities and disposable simulator; first attempt timed out; no real terrain or UI.')
slope_dir = root / 'sitl-evidence/command-ack-terrain_slope'
slope = json.loads((slope_dir / 'summary.json').read_text())
slope_relay = json.loads((slope_dir / 'relay-result.json').read_text())
slope_log = (slope_dir / 'probe.log').read_text(encoding='utf-8')
slope_fixture = root / 'sitl-evidence/terrain-slope-fixture-data/S36E149.hgt'
def slope_offset(lat, lon, east, north):
    phi, lam = math.radians(lat), math.radians(lon)
    bearing, dr = math.atan2(east, north), math.hypot(east, north) / 6378100.0
    phi2 = math.asin(math.sin(phi) * math.cos(dr) + math.cos(phi) * math.sin(dr) * math.cos(bearing))
    lam2 = lam + math.atan2(math.sin(bearing) * math.sin(dr) * math.cos(phi), math.cos(dr) - math.sin(phi) * math.sin(phi2))
    return math.degrees(phi2), math.degrees(lam2)
def slope_height(lat, lon):
    return 1200 * (1 - (lat + 36)) + 2400 * (lon - 149)
slope_errors = []
slope_swapped = 0
for block in slope['data']:
    bit, spacing = block['gridbit'], block['grid_spacing']
    lat, lon = slope_offset(block['lat'] / 1e7, block['lon'] / 1e7, 4 * spacing * (bit % 8), 4 * spacing * (bit // 8))
    for i, observed in enumerate(block['data']):
        expected = int(slope_height(*slope_offset(lat, lon, spacing * (i % 4), spacing * (i // 4))))
        swapped = int(slope_height(*slope_offset(lat, lon, spacing * (i // 4), spacing * (i % 4))))
        slope_errors.append(abs(observed - expected))
        slope_swapped += observed != swapped
check('SITL synthetic sloped terrain', slope['relay'] == slope_relay and slope_relay['case'] == 'terrain_slope' and
      slope_relay['errors'] == [] and slope_relay['closed_by'] == 'client' and slope_relay['buffered_bytes_at_close'] == 0 and
      slope_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((slope_dir / name).read_bytes()).hexdigest() == digest for name, digest in slope_relay['capture_sha256'].items()) and
      slope['fixture_sha256'] == hashlib.sha256(slope_fixture.read_bytes()).hexdigest() == 'e94fa1713b8ebde9e83b48273226ee5c0b913523a0be746f28d55b577ea89fcd' and
      slope['probe_source_sha256'] == hashlib.sha256((slope_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      slope['probe_exe_sha256'] == hashlib.sha256((slope_dir / 'probe.exe').read_bytes()).hexdigest() and
      slope['probe_log_sha256'] == hashlib.sha256((slope_dir / 'probe.log').read_bytes()).hexdigest() and
      slope['library_hashes']['original_ardupilot'] == slope['library_hashes']['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      slope['library_hashes']['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      slope['library_hashes']['original_utilities'] != slope['library_hashes']['test_utilities'] and
      slope['library_hashes']['original_utilities'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      slope['library_hashes']['test_utilities'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      len(slope['data']) == 41 and len(slope_errors) == slope['sample_comparisons'] == 656 and max(slope_errors) == slope['max_sample_error_m'] == 0 and
      slope_swapped == slope['swapped_axis_differences'] == 492 and
      all(any(m['lat'] == r['lat'] and m['lon'] == r['lon'] and m['grid_spacing'] == r['grid_spacing'] and (r['mask'] & (1 << m['gridbit']))
              for r in slope['requests']) for m in slope['data']) and
      abs(slope['matched_home_report']['terrain_height'] - slope_height(-35.363261, 149.165230)) <= 1 and
      slope['matched_home_report'] in slope['reports'] and (slope_dir / 'probe-exit.txt').read_text().strip() == '0' and
      bool(slope['heartbeats']) and all(not (m['base_mode'] & 128) for m in slope['heartbeats']) and
      all(line in slope_log for line in slope['verified_probe_lines']),
      'Synthetic slope and patched Utilities in disposable SITL; no real terrain or flight.')
terrain_void_dir = root / 'sitl-evidence/command-ack-terrain_invalid'
terrain_void = json.loads((terrain_void_dir / 'summary.json').read_text())
terrain_void_relay = json.loads((terrain_void_dir / 'relay-result.json').read_text())
terrain_void_log = (terrain_void_dir / 'probe.log').read_text(encoding='utf-8')
terrain_void_fixture = root / 'sitl-evidence/terrain-invalid-fixture-data/S36E149.hgt'
check('SITL all-void terrain fixture', terrain_void['relay'] == terrain_void_relay and terrain_void_relay['case'] == 'terrain_invalid' and
      terrain_void_relay['errors'] == [] and terrain_void_relay['closed_by'] == 'client' and terrain_void_relay['buffered_bytes_at_close'] == 0 and
      terrain_void_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((terrain_void_dir / name).read_bytes()).hexdigest() == digest for name, digest in terrain_void_relay['capture_sha256'].items()) and
      terrain_void['fixture_sha256'] == hashlib.sha256(terrain_void_fixture.read_bytes()).hexdigest() == '2b0abd7479e57d9402b8beceda539d7e758702b887028e39aac2cd58475280b5' and
      terrain_void_fixture.read_bytes() == bytes([128, 0]) * (1201 * 1201) and
      terrain_void['probe_source_sha256'] == hashlib.sha256((terrain_void_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      terrain_void['probe_exe_sha256'] == hashlib.sha256((terrain_void_dir / 'probe.exe').read_bytes()).hexdigest() and
      terrain_void['probe_log_sha256'] == hashlib.sha256((terrain_void_dir / 'probe.log').read_bytes()).hexdigest() and
      terrain_void['library_hashes']['original_ardupilot'] == terrain_void['library_hashes']['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      terrain_void['library_hashes']['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      terrain_void['library_hashes']['original_utilities'] != terrain_void['library_hashes']['test_utilities'] and
      terrain_void['library_hashes']['original_utilities'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      terrain_void['library_hashes']['test_utilities'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      len(terrain_void['requests']) >= 2 and not terrain_void['data'] and bool(terrain_void['reports']) and
      all(m['pending'] > 0 and m['loaded'] == 0 for m in terrain_void['reports']) and
      any(m['req_stream_id'] == 0 and m['req_message_rate'] == 4 and m['start_stop'] == 1 for m in terrain_void['streams']) and
      bool(terrain_void['heartbeats']) and all(not (m['base_mode'] & 128) for m in terrain_void['heartbeats']) and
      all(line in terrain_void_log for line in terrain_void['verified_probe_lines']) and (terrain_void_dir / 'probe-exit.txt').read_text().strip() == '0',
      'Synthetic all-void tile and patched Utilities in disposable SITL; finite observation, no real terrain or flight.')
terrain_retry_dir = root / 'sitl-evidence/command-ack-terrain_drop_one'
terrain_retry = json.loads((terrain_retry_dir / 'summary.json').read_text())
terrain_retry_relay = json.loads((terrain_retry_dir / 'relay-result.json').read_text())
terrain_retry_log = (terrain_retry_dir / 'probe.log').read_text(encoding='utf-8')
check('SITL dropped terrain block retry', terrain_retry['relay'] == terrain_retry_relay and
      terrain_retry_relay['case'] == 'terrain_drop_one' and terrain_retry_relay['errors'] == [] and
      terrain_retry_relay['closed_by'] == 'client' and terrain_retry_relay['buffered_bytes_at_close'] == 0 and terrain_retry_relay['dropped_terrain'] == 1 and
      terrain_retry_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((terrain_retry_dir / name).read_bytes()).hexdigest() == digest for name, digest in terrain_retry_relay['capture_sha256'].items()) and
      terrain_retry['fixture_sha256'] == hashlib.sha256(terrain_fixture.read_bytes()).hexdigest() and
      terrain_retry['probe_source_sha256'] == hashlib.sha256((terrain_retry_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      terrain_retry['probe_exe_sha256'] == hashlib.sha256((terrain_retry_dir / 'probe.exe').read_bytes()).hexdigest() and
      terrain_retry['probe_log_sha256'] == hashlib.sha256((terrain_retry_dir / 'probe.log').read_bytes()).hexdigest() and
      terrain_retry['relay_source_sha256'] == hashlib.sha256((terrain_retry_dir / 'relay-source.py').read_bytes()).hexdigest() and
      terrain_retry['library_hashes']['original_ardupilot'] == terrain_retry['library_hashes']['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      terrain_retry['library_hashes']['test_ardupilot'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      terrain_retry['library_hashes']['original_utilities'] != terrain_retry['library_hashes']['test_utilities'] and
      terrain_retry['library_hashes']['original_utilities'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      terrain_retry['library_hashes']['test_utilities'] == hashlib.sha256((root / 'mission-planner-isolated/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      len(terrain_retry['dropped']) == 1 and terrain_retry['sent'][0] == terrain_retry['dropped'][0] and
      terrain_retry['sent'][1:] == terrain_retry['delivered'] and terrain_retry['dropped'][0]['gridbit'] == 0 and
      all(m['data'] == [321] * 16 for m in terrain_retry['sent']) and bool(terrain_retry['matching_deliveries']) and
      all(m in terrain_retry['delivered'] and (m['lat'], m['lon'], m['grid_spacing'], m['gridbit']) ==
          (terrain_retry['dropped'][0]['lat'], terrain_retry['dropped'][0]['lon'], terrain_retry['dropped'][0]['grid_spacing'], 0)
          for m in terrain_retry['matching_deliveries']) and len(terrain_retry['matching_requests']) >= 2 and
      all((m['lat'], m['lon'], m['grid_spacing']) == (terrain_retry['dropped'][0]['lat'], terrain_retry['dropped'][0]['lon'], terrain_retry['dropped'][0]['grid_spacing']) and (m['mask'] & 1)
          for m in terrain_retry['matching_requests']) and
      any(m['mask'] == 1 for m in terrain_retry['matching_requests']) and
      any(m['lat'] == -353632610 and m['lon'] == 1491652300 and m['terrain_height'] == 321 for m in terrain_retry['reports']) and
      bool(terrain_retry['heartbeats']) and all(not (m['base_mode'] & 128) for m in terrain_retry['heartbeats']) and
      all(line in terrain_retry_log for line in terrain_retry['verified_probe_lines']) and (terrain_retry_dir / 'probe-exit.txt').read_text().strip() == '0',
      'One deliberately dropped synthetic block; matching retransmission captured, no per-block vehicle acknowledgement or real terrain.')
for fence_case in ('fence_roundtrip', 'fence_roundtrip_retry', 'fence_roundtrip_stable', 'fence_highlevel'):
    fence_dir = root / 'sitl-evidence' / ('command-ack-' + fence_case)
    fence_summary = json.loads((fence_dir / 'summary.json').read_text())
    fence_relay = json.loads((fence_dir / 'relay-result.json').read_text())
    fence_log = (fence_dir / 'probe.log').read_text(encoding='utf-8')
    fence_out = [m for m in fence_summary['sent'] if m['mission_type'] == 1]
    fence_in = [m for m in fence_summary['received'] if m['mission_type'] == 1]
    normal_in = [m for m in fence_summary['received'] if m['mission_type'] == 0]
    fence_expected = [(0, 5001, 3, -353640000, 1491639999), (1, 5001, 3, -353620000, 1491639999),
                      (2, 5001, 3, -353630000, 1491670000), (3, 5004, 25, -353630000, 1491658000)]
    check('SITL typed fence roundtrip ' + fence_case, fence_summary['relay'] == fence_relay and fence_relay['case'] == fence_case and
          fence_relay['errors'] == [] and fence_relay['closed_by'] == 'client' and fence_relay['buffered_bytes_at_close'] == 0 and
          fence_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((fence_dir / name).read_bytes()).hexdigest() == digest for name, digest in fence_relay['capture_sha256'].items()) and
          fence_summary['probe_source_sha256'] == hashlib.sha256((fence_dir / 'probe-source.cs').read_bytes()).hexdigest() and
          fence_summary['probe_exe_sha256'] == hashlib.sha256((fence_dir / 'probe.exe').read_bytes()).hexdigest() and
          fence_summary['probe_log_sha256'] == hashlib.sha256((fence_dir / 'probe.log').read_bytes()).hexdigest() and
          all(fence_summary['library_hashes'][name] == hashlib.sha256((root / path).read_bytes()).hexdigest() for name, path in
              [('ardupilot', 'mission-planner-portable/MissionPlanner.ArduPilot.dll'), ('utilities', 'mission-planner-portable/MissionPlanner.Utilities.dll'), ('mavlink', 'mission-planner-portable/MAVLink.dll')]) and
          bool(fence_summary['heartbeats']) and all(not (m['base_mode'] & 128) for m in fence_summary['heartbeats']) and
          all(line in fence_log for line in fence_summary['verified_probe_lines']) and
          ((fence_case == 'fence_roundtrip' and (fence_dir / 'probe-exit.txt').read_text().strip() == '1' and not fence_out and
            'ERROR=System.Exception: item mismatch MISSION:0' in fence_log and len(normal_in) == 1 and normal_in[0]['x'] == normal_in[0]['y'] == 0) or
           (fence_case != 'fence_roundtrip' and (fence_dir / 'probe-exit.txt').read_text().strip() == '0' and
            [(m['mission_type'], m['count']) for m in fence_summary['counts']] == [(0, 2), (1, 4)] and
            [(m['seq'], m['command'], m['param1'], m['x'], m['y']) for m in fence_out] == fence_expected and
            [(m['seq'], m['command'], m['param1'], m['x'], m['y']) for m in fence_in] == fence_expected and
            all(m['autocontinue'] == 1 for m in fence_out) and all(m['autocontinue'] == 0 for m in fence_in) and
            [(m['mission_type'], m['type']) for m in fence_summary['acks']] == [(0, 0), (1, 0)] and
            len(normal_in) == 4 and normal_in[:2] == normal_in[2:] and
            (normal_in[1]['x'], normal_in[1]['y'], normal_in[1]['z']) == (-353630000, 1491655000, 20))),
          'Original library, disposable SITL; selected item fields; first probe failed on mission-home assumption; no full UI or fence enforcement.')
for reboot_case, baseline_case in (('fence-mission-reboot', 'fence_roundtrip_retry'), ('fence-mission-reboot-stable', 'fence_roundtrip_stable')):
    reboot_dir = root / 'sitl-evidence' / reboot_case
    reboot_summary = json.loads((reboot_dir / 'summary.json').read_text())
    reboot_result = json.loads((reboot_dir / 'result.json').read_text())
    reboot_baseline = root / 'sitl-evidence' / ('command-ack-' + baseline_case)
    check('SITL typed fence reboot ' + reboot_case, reboot_summary['result'] == reboot_result and
          reboot_result['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          reboot_summary['source_summary_sha256'] == reboot_result['source_summary_sha256'] == hashlib.sha256((reboot_baseline / 'summary.json').read_bytes()).hexdigest() and
          reboot_summary['readback_source_sha256'] == hashlib.sha256((reboot_dir / 'readback-source.py').read_bytes()).hexdigest() and
          reboot_result['source_storage_sha256'] == reboot_result['copied_storage_sha256'] == hashlib.sha256((reboot_dir / 'eeprom-before.bin').read_bytes()).hexdigest() ==
          hashlib.sha256((reboot_baseline / 'eeprom.bin').read_bytes()).hexdigest() and
          reboot_result['post_shutdown_storage_sha256'] == hashlib.sha256((reboot_dir / 'eeprom.bin').read_bytes()).hexdigest() and
          reboot_result['downlink_sha256'] == hashlib.sha256((reboot_dir / 'downlink.bin').read_bytes()).hexdigest() and
          ((reboot_case == 'fence-mission-reboot' and reboot_result['errors'] == ["RuntimeError('missing item (0, 1)')"] and
            [(m['mission_type'], m['seq']) for m in reboot_summary['items']] == [(0, 0)] and
            any(m['mission_type'] == 0 and m['type'] == 1 for m in reboot_summary['acks'])) or
           (reboot_case == 'fence-mission-reboot-stable' and reboot_result['errors'] == [] and reboot_result['startup_wait_seconds'] == 12 and
            reboot_result['expected'] == reboot_result['observed'] and len(reboot_result['observed']['0']) == 2 and len(reboot_result['observed']['1']) == 4 and
            [(m['mission_type'], m['seq']) for m in reboot_summary['items']] == [(0, 0), (0, 1), (1, 0), (1, 1), (1, 2), (1, 3)])),
          'Copied simulator storage and standalone MAVLink readback; first attempt failed and cause is not established.')
cap_dir = root / 'sitl-evidence/fence-capability-synthetic'
cap = json.loads((cap_dir / 'summary.json').read_text())
cap_lines = (cap_dir / 'probe.log').read_text(encoding='utf-8').splitlines()
check('Synthetic fence and rally capability guards', cap_lines == cap['lines'] == [
      'FENCE_UPLOAD=Fence mission items not supported, please use legacy geofence BYTES=0',
      'FENCE_DOWNLOAD=Fence mission items not supported, please use legacy geofence BYTES=0',
      'RALLY_UPLOAD=Mission type only supported under mavlink2 BYTES=0',
      'RALLY_DOWNLOAD=Mission type only supported under mavlink2 BYTES=0'] and
      (cap_dir / 'probe-initial.log').read_text(encoding='utf-8').splitlines() == cap_lines and
      (cap_dir / 'capture.bin').read_bytes() == b'' and cap['capture_sha256'] == hashlib.sha256((cap_dir / 'capture.bin').read_bytes()).hexdigest() and
      cap['probe_log_sha256'] == hashlib.sha256((cap_dir / 'probe.log').read_bytes()).hexdigest() and
      cap['probe_source_sha256'] == hashlib.sha256((cap_dir / 'probe-source.cs').read_bytes()).hexdigest() and
      cap['transport_source_sha256'] == hashlib.sha256((cap_dir / 'transport-source.cs').read_bytes()).hexdigest() and
      cap['probe_exe_sha256'] == hashlib.sha256((cap_dir / 'probe.exe').read_bytes()).hexdigest() and
      cap['library_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest(),
      'In-memory transport, zero capabilities and MAVLink 1; no simulator or full UI.')
legacy_expected = [(-35.363261,149.165230), (-35.364,149.164), (-35.362,149.164), (-35.363,149.167), (-35.364,149.164)]
def fence_distance(lat1, lon1, lat2, lon2):
    value = math.sin(math.radians(lat2-lat1)/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(math.radians(lon2-lon1)/2)**2
    return 2 * 6371000 * math.asin(math.sqrt(value))
for legacy_case in ('fence_legacy', 'fence_legacy_retry', 'fence_legacy_release'):
    legacy_dir = root / 'sitl-evidence' / ('command-ack-' + legacy_case)
    legacy = json.loads((legacy_dir / 'summary.json').read_text())
    legacy_relay = json.loads((legacy_dir / 'relay-result.json').read_text())
    legacy_log = (legacy_dir / 'probe.log').read_text(encoding='utf-8', errors='replace')
    legacy_binary = root / ('sitl-evidence/arducopter' if legacy_case == 'fence_legacy_release' else 'sitl-evidence/archive-built/arducopter')
    check('SITL legacy fence ' + legacy_case, legacy['relay'] == legacy_relay and legacy_relay['case'] == legacy_case and
          legacy_relay['errors'] == [] and legacy_relay['closed_by'] == 'client' and legacy_relay['buffered_bytes_at_close'] == 0 and
          legacy['binary_sha256'] == legacy_relay['binary_sha256'] == hashlib.sha256(legacy_binary.read_bytes()).hexdigest() and
          all(hashlib.sha256((legacy_dir / name).read_bytes()).hexdigest() == digest for name, digest in legacy_relay['capture_sha256'].items()) and
          legacy['probe_source_sha256'] == hashlib.sha256((legacy_dir / 'probe-source.cs').read_bytes()).hexdigest() and
          legacy['probe_exe_sha256'] == hashlib.sha256((legacy_dir / 'probe.exe').read_bytes()).hexdigest() and
          legacy['probe_log_sha256'] == hashlib.sha256((legacy_dir / 'probe.log').read_bytes()).hexdigest() and
          all(legacy['library_hashes'][name] == hashlib.sha256((root / path).read_bytes()).hexdigest() for name, path in
              [('ardupilot', 'mission-planner-portable/MissionPlanner.ArduPilot.dll'), ('utilities', 'mission-planner-portable/MissionPlanner.Utilities.dll'),
               ('mavlink', 'mission-planner-portable/MAVLink.dll'), ('valuetuple', 'mission-planner-portable/System.ValueTuple.dll')]) and
          bool(legacy['versions']) and all(m['flight_sw_version'] == (0x040702ff if legacy_case == 'fence_legacy_release' else 0x04080000) for m in legacy['versions']) and
          bool(legacy['heartbeats']) and all(not (m['base_mode'] & 128) for m in legacy['heartbeats']) and
          any(m['param_id'] == 'FENCE_TOTAL' and m['param_value'] == 5 for m in legacy['sets']) and
          any(m['param_id'] == 'FENCE_TOTAL' and m['param_value'] == 5 for m in legacy['params']) and
          all(line in legacy_log for line in legacy['verified_probe_lines']) and
          ((legacy_case == 'fence_legacy_release' and (legacy_dir / 'probe-exit.txt').read_text().strip() == '0' and
            [m['idx'] for m in legacy['points']] == list(range(5)) and [m['idx'] for m in legacy['fetches']] == list(range(5)) * 2 and
            [m['idx'] for m in legacy['received']] == list(range(5)) * 2 and
            any('FENCE_FETCH_POINT' in m['text'] and 'deprecated' in m['text'] for m in legacy['notices']) and
            all(m['count'] == 5 and fence_distance(m['lat'], m['lng'], *legacy_expected[m['idx']]) < 5 for m in legacy['received'])) or
           (legacy_case != 'fence_legacy_release' and (legacy_dir / 'probe-exit.txt').read_text().strip() == '1' and
            [m['idx'] for m in legacy['points']] == [0] and [m['idx'] for m in legacy['fetches']] == [0, 0, 0, 0] and not legacy['received'])),
          'Selected Copter SITL binaries and setup; two source-built runs timed out, prebuilt run read back five points; no full UI.')
comparison = json.loads((root / 'sitl-evidence/legacy-fence-source/comparison.json').read_text())
def git_blob(path):
    data = path.read_bytes()
    return hashlib.sha1(('blob ' + str(len(data)) + '\0').encode() + data).hexdigest()
candidate_tree = json.loads((root / 'research-tools/archive-candidate-tree.json').read_text())
candidate_entries = {item['path']: item['sha'] for item in candidate_tree['tree']}
check('Legacy fence source and binary comparison',
      comparison['old_source_commit'] == 'fb773567896014da007bca58358704d4a0d8516f' and
      comparison['new_source_commit'] == candidate_tree['sha'] == '72b238201f5ea3b556e3809b2ec704fcf701474a' and
      len(comparison['files']) == 5 and all(
          git_blob(root / row['old_file']) == row['old_git_blob_sha1'] and
          git_blob(root / 'ardupilot-source/ardupilot-master' / row['repository_path']) == row['new_git_blob_sha1'] == candidate_entries[row['repository_path']]
          for row in comparison['files']) and
      all(hashlib.sha256((root / path).read_bytes()).hexdigest() == comparison['binaries'][name]['sha256'] for name, path in
          [('prebuilt_4_7_2', 'sitl-evidence/arducopter'), ('source_built_4_8_dev', 'sitl-evidence/archive-built/arducopter')]) and
      'MAVLINK_MSG_ID_FENCE_FETCH_POINT' in (root / 'sitl-evidence/legacy-fence-source/GCS_Fence.cpp').read_text() and
      'MAVLINK_MSG_ID_FENCE_FETCH_POINT' not in (root / 'ardupilot-source/ardupilot-master/libraries/GCS_MAVLink/GCS_Common.cpp').read_text(),
      'Pinned source comparison and selected binary hashes; older binary exact build provenance remains unknown.')
interop_dir = root / 'sitl-evidence/command-ack-fence_legacy_interop'
interop = json.loads((interop_dir / 'summary.json').read_text())
interop_relay = json.loads((interop_dir / 'relay-result.json').read_text())
interop_log = (interop_dir / 'probe-retry.log').read_text(encoding='utf8', errors='replace')
check('SITL legacy to typed fence readback',
      interop['relay'] == interop_relay and interop_relay['errors'] == [] and
      interop_relay['closed_by'] == 'client' and interop_relay['buffered_bytes_at_close'] == 0 and
      interop_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((interop_dir / name).read_bytes()).hexdigest() == digest for name, digest in interop_relay['capture_sha256'].items()) and
      all(hashlib.sha256((interop_dir / name).read_bytes()).hexdigest() == digest for name, digest in interop['hashes'].items()) and
      all(hashlib.sha256((root / 'mission-planner-portable' / name).read_bytes()).hexdigest() == digest for name, digest in interop['library_hashes'].items()) and
      (interop_dir / 'probe-exit.txt').read_text().strip() == '1' and (interop_dir / 'probe-retry-exit.txt').read_text().strip() == '0' and
      [m['idx'] for m in interop['points']] == list(range(5)) and
      [m['idx'] for m in interop['responses']] == list(range(5)) * 2 and
      [m['seq'] for m in interop['typed_requests']] == list(range(4)) and
      [m['command'] for m in interop['typed_items']] == [5000, 5001, 5001, 5001] and
      [m['param1'] for m in interop['typed_items']] == [0, 3, 3, 3] and
      all(fence_distance(m['x']/1e7, m['y']/1e7, *legacy_expected[i]) < 5 for i,m in enumerate(interop['typed_items'])) and
      interop['heartbeats'] and all(not (m['base_mode'] & 128) for m in interop['heartbeats']) and
      all(line in interop_log for line in ('LEGACY_ROUNDTRIP=True', 'TYPED_COUNT=4', 'INTEROP_READ=True')),
      'One disarmed Copter 4.7.2 run; legacy closed triangle read through typed fence mission.')
reverse_dir = root / 'sitl-evidence/command-ack-fence_typed_legacy'
reverse = json.loads((reverse_dir / 'summary.json').read_text())
reverse_relay = json.loads((reverse_dir / 'relay-result.json').read_text())
check('SITL typed to legacy fence readback',
      reverse['relay'] == reverse_relay and reverse_relay['errors'] == [] and reverse_relay['closed_by'] == 'client' and
      reverse_relay['buffered_bytes_at_close'] == 0 and
      reverse_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((reverse_dir / name).read_bytes()).hexdigest() == digest for name,digest in reverse_relay['capture_sha256'].items()) and
      all(hashlib.sha256((reverse_dir / name).read_bytes()).hexdigest() == digest for name,digest in reverse['hashes'].items()) and
      all(hashlib.sha256((root / 'mission-planner-portable' / name).read_bytes()).hexdigest() == digest for name,digest in reverse['library_hashes'].items()) and
      (reverse_dir / 'probe-exit.txt').read_text().strip() == '0' and
      [m['seq'] for m in reverse['typed_items']] == list(range(4)) and
      [m['command'] for m in reverse['typed_items']] == [5000,5001,5001,5001] and
      [m['param1'] for m in reverse['typed_items']] == [0,3,3,3] and
      all(fence_distance(m['x']/1e7,m['y']/1e7,*legacy_expected[i]) < 5 for i,m in enumerate(reverse['typed_items'])) and
      [m['idx'] for m in reverse['fetches']] == list(range(5)) == [m['idx'] for m in reverse['points']] and
      all(m['count'] == 5 and fence_distance(m['lat'],m['lng'],*legacy_expected[i]) < 5 for i,m in enumerate(reverse['points'])) and
      reverse['heartbeats'] and all(not (m['base_mode'] & 128) for m in reverse['heartbeats']) and
      'REVERSE_INTEROP_READ=True' in (reverse_dir / 'probe.log').read_text(encoding='utf8',errors='replace'),
      'One disarmed Copter 4.7.2 run; typed inclusion triangle read through legacy protocol.')
advanced_dir = root / 'sitl-evidence/command-ack-fence_advanced_legacy'
advanced = json.loads((advanced_dir / 'summary.json').read_text())
advanced_relay = json.loads((advanced_dir / 'relay-result.json').read_text())
advanced_fields = ['seq','command','param1','param2','param3','param4','x','y','z','mission_type']
check('SITL advanced fence legacy rejection and typed readback',
      advanced['relay'] == advanced_relay and advanced_relay['errors'] == [] and
      advanced_relay['closed_by'] == 'client' and advanced_relay['buffered_bytes_at_close'] == 0 and
      advanced_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((advanced_dir / name).read_bytes()).hexdigest() == digest for name,digest in advanced_relay['capture_sha256'].items()) and
      all(hashlib.sha256((advanced_dir / name).read_bytes()).hexdigest() == digest for name,digest in advanced['hashes'].items()) and
      all(hashlib.sha256((root / 'mission-planner-portable' / name).read_bytes()).hexdigest() == digest for name,digest in advanced['library_hashes'].items()) and
      (advanced_dir / 'probe-exit.txt').read_text().strip() == '0' and
      [m['seq'] for m in advanced['uploads']] == list(range(5)) == [m['seq'] for m in advanced['readback']] and
      [m['command'] for m in advanced['uploads']] == [5000,5001,5001,5001,5004] and
      [m['param1'] for m in advanced['uploads']] == [0,3,3,3,25] and
      advanced['compared_fields'] == advanced_fields and
      all(all(a[field] == b[field] for field in advanced_fields) for a,b in zip(advanced['uploads'],advanced['readback'])) and
      [m['idx'] for m in advanced['fetches']] == [0,0,0,0] and advanced['responses'] == [] and
      len(advanced['warnings']) >= 1 and all('Vehicle contains advanced fences' in m['text'] for m in advanced['warnings']) and
      advanced['heartbeats'] and all(not (m['base_mode'] & 128) for m in advanced['heartbeats']) and
      all(line in (advanced_dir / 'probe.log').read_text(encoding='utf8',errors='replace') for line in
          ('LEGACY_ERROR=System.TimeoutException:Timeout on read - getFencePoint','TYPED_COUNT=5','ADVANCED_PROBE_COMPLETE=True')),
      'One disarmed Copter 4.7.2 run; legacy fetch refused with advanced fence warning; selected typed item fields preserved.')
write_dir = root / 'sitl-evidence/command-ack-fence_advanced_write'
write_test = json.loads((write_dir / 'summary.json').read_text())
write_relay = json.loads((write_dir / 'relay-result.json').read_text())
check('SITL legacy write replaces advanced fence',
      write_test['relay'] == write_relay and not write_relay['errors'] and write_relay['closed_by'] == 'client' and
      write_relay['buffered_bytes_at_close'] == 0 and
      write_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((write_dir / name).read_bytes()).hexdigest() == digest for name,digest in write_relay['capture_sha256'].items()) and
      all(hashlib.sha256((write_dir / name).read_bytes()).hexdigest() == digest for name,digest in write_test['hashes'].items()) and
      all(hashlib.sha256((root / 'mission-planner-portable' / name).read_bytes()).hexdigest() == digest for name,digest in write_test['library_hashes'].items()) and
      (write_dir / 'probe-exit.txt').read_text().strip() == '0' and
      [m['seq'] for m in write_test['uploads']] == list(range(5)) and
      [m['command'] for m in write_test['uploads']] == [5000,5001,5001,5001,5004] and
      [m['param1'] for m in write_test['uploads']] == [0,3,3,3,25] and any(m['type'] == 0 for m in write_test['acks']) and
      len(write_test['writes']) == len(write_test['fetches']) == len(write_test['responses']) == 1 and
      write_test['writes'][0]['idx'] == 0 and write_test['writes'][0]['count'] == 6 and
      write_test['fetches'][0]['idx'] == 0 and len(write_test['counts']) == 1 and write_test['counts'][0]['count'] == 1 and
      len(write_test['readback']) == 1 and write_test['readback'][0]['command'] == 5000 and
      fence_distance(write_test['readback'][0]['x']/1e7,write_test['readback'][0]['y']/1e7,-35.3635,149.1655) < 5 and
      write_test['heartbeats'] and all(not(m['base_mode'] & 128) for m in write_test['heartbeats']) and
      all(line in (write_dir / 'probe.log').read_text(encoding='utf8',errors='replace') for line in
          ('LEGACY_TOTAL=6','LEGACY_WRITE_RESULT=True','TYPED_COUNT=1','ADVANCED_PROBE_COMPLETE=True')),
      'One disarmed Copter 4.7.2 run; after a single legacy write, typed readback contained one return point.')
for ftp_case in ('fence_mavftp','fence_mavftp_pumped'):
    ftp_dir = root / 'sitl-evidence' / ('command-ack-' + ftp_case)
    ftp_result = json.loads((ftp_dir / 'summary.json').read_text())
    ftp_relay = json.loads((ftp_dir / 'relay-result.json').read_text())
    ftp_log = (ftp_dir / 'probe.log').read_text(encoding='utf8',errors='replace')
    ftp_fields = ['param1','param2','param3','param4','x','y','z','command','frame']
    ftp_writes = [m['ftp'] for m in ftp_result['ftp_up'] if m['ftp']['opcode'] == 7]
    ftp_chunks = [m['ftp'] for m in ftp_result['ftp_down'] if m['ftp']['opcode'] == 128 and m['ftp']['request_opcode'] == 15]
    check('SITL fence MAVFTP ' + ftp_case,
          ftp_result['relay'] == ftp_relay and ftp_relay['case'] == ftp_case and not ftp_relay['errors'] and
          ftp_relay['closed_by'] == 'client' and ftp_relay['buffered_bytes_at_close'] == 0 and
          ftp_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((ftp_dir / name).read_bytes()).hexdigest() == digest for name,digest in ftp_relay['capture_sha256'].items()) and
          all(hashlib.sha256((ftp_dir / name).read_bytes()).hexdigest() == digest for name,digest in ftp_result['hashes'].items()) and
          all(hashlib.sha256((root / 'mission-planner-portable' / name).read_bytes()).hexdigest() == digest for name,digest in ftp_result['library_hashes'].items()) and
          ftp_result['heartbeats'] and all(not(m['base_mode'] & 128) for m in ftp_result['heartbeats']) and
          [m['command'] for m in ftp_result['upload']] == [5001,5001,5001,5004] and
          [m['param1'] for m in ftp_result['upload']] == [3,3,3,25] and 'FTP_UPLOAD_RETURNED=True BYTES=162' in ftp_log and
          ((ftp_case == 'fence_mavftp' and (ftp_dir / 'probe-exit.txt').read_text().strip() == '1' and
            'MISSION_COUNT=0' in ftp_log and 'ERROR=System.NullReferenceException' in ftp_log) or
           (ftp_case == 'fence_mavftp_pumped' and (ftp_dir / 'probe-exit.txt').read_text().strip() == '0' and
            [m['ftp']['opcode'] for m in ftp_result['ftp_up']] == [2,6,7,7,7,2,2,4,15] and
            bytes.fromhex(ftp_result['ftp_up'][1]['ftp']['data_hex']) == b'@MISSION/fence.dat' and
            [m['offset'] for m in ftp_writes] == [0,80,160] and
            b''.join(bytes.fromhex(m['data_hex']) for m in ftp_writes) == (ftp_dir / 'upload.dat').read_bytes() and
            [m['offset'] for m in ftp_chunks] == [0,110] and
            b''.join(bytes.fromhex(m['data_hex']) for m in ftp_chunks) == (ftp_dir / 'download.dat').read_bytes() and
            ftp_result['compared_fields'] == ftp_fields and
            all(all(a[f] == b[f] == c[f] for f in ftp_fields) for a,b,c in zip(ftp_result['upload'],ftp_result['download'],ftp_result['mission_items'])) and
            len(ftp_result['download']) == len(ftp_result['mission_items']) == 4 and
            [m['seq'] for m in ftp_result['download']] == list(range(4)) and
            [m['mission_type'] for m in ftp_result['download']] == [1]*4 and 'FTP_PROBE_COMPLETE=True' in ftp_log)),
          'Original libraries with and without harness packet pump; disarmed source-built Copter SITL, no planner UI.')
ftp_drop_dir = root / 'sitl-evidence/command-ack-fence_mavftp_drop_writes'
ftp_drop = json.loads((ftp_drop_dir / 'summary.json').read_text())
ftp_drop_relay = json.loads((ftp_drop_dir / 'relay-result.json').read_text())
ftp_drop_fields = ['seq','command','param1','param2','param3','param4','x','y','z','mission_type']
check('SITL MAVFTP dropped fence writes',
      ftp_drop['relay'] == ftp_drop_relay and ftp_drop_relay['case'] == 'fence_mavftp_drop_writes' and
      not ftp_drop_relay['errors'] and ftp_drop_relay['closed_by'] == 'client' and ftp_drop_relay['buffered_bytes_at_close'] == 0 and
      ftp_drop_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      all(hashlib.sha256((ftp_drop_dir / name).read_bytes()).hexdigest() == digest for name,digest in ftp_drop_relay['capture_sha256'].items()) and
      all(hashlib.sha256((ftp_drop_dir / name).read_bytes()).hexdigest() == digest for name,digest in ftp_drop['hashes'].items()) and
      all(hashlib.sha256((root / 'mission-planner-portable' / name).read_bytes()).hexdigest() == digest for name,digest in ftp_drop['library_hashes'].items()) and
      (ftp_drop_dir / 'probe-exit.txt').read_text().strip() == '0' and ftp_drop_relay['dropped_ftp_writes'] == 30 and
      len(ftp_drop['dropped']) == 30 and all(m['ftp']['opcode'] == 7 and m['ftp']['offset'] == 0 for m in ftp_drop['dropped']) and
      [m for m in ftp_drop['ftp_input'] if m['ftp']['opcode'] == 7] == ftp_drop['dropped'] and
      not any(m['ftp']['opcode'] == 7 for m in ftp_drop['ftp_delivered']) and
      any(m['ftp']['opcode'] == 6 and bytes.fromhex(m['ftp']['data_hex']) == b'@MISSION/fence.dat' for m in ftp_drop['ftp_delivered']) and
      any(m['ftp']['opcode'] == 128 and m['ftp']['request_opcode'] == 6 for m in ftp_drop['ftp_responses']) and
      [m['seq'] for m in ftp_drop['baseline']] == list(range(4)) == [m['seq'] for m in ftp_drop['readback']] and
      [m['param1'] for m in ftp_drop['baseline']] == [3,3,3,15] and ftp_drop['replacement_last_radius'] == 25 and
      ftp_drop['compared_fields'] == ftp_drop_fields and
      all(all(a[f] == b[f] for f in ftp_drop_fields) for a,b in zip(ftp_drop['baseline'],ftp_drop['readback'])) and
      ftp_drop['heartbeats'] and all(not(m['base_mode'] & 128) for m in ftp_drop['heartbeats']) and
      all(line in (ftp_drop_dir / 'probe.log').read_text(encoding='utf8',errors='replace') for line in
          ('FTP_UPLOAD_RETURNED=True BYTES=162','MISSION_COUNT=4','DROP_PROBE_COMPLETE=True')),
      'Disarmed source-built Copter SITL; all 30 MAVFTP write requests dropped; earlier fence read back after normal return.')
for loss_case in ('fence_mavftp_partial','fence_mavftp_last_ack','fence_mavftp_last_ack_fixed','fence_mavftp_last_ack_retry'):
    loss_dir = root / 'sitl-evidence' / ('command-ack-' + loss_case)
    loss = json.loads((loss_dir / 'summary.json').read_text())
    loss_relay = json.loads((loss_dir / 'relay-result.json').read_text())
    loss_fields = ['command','param1','param2','param3','param4','x','y','z']
    is_partial = loss_case == 'fence_mavftp_partial'
    is_retry = loss_case == 'fence_mavftp_last_ack_retry'
    source_items = loss['baseline'] if is_partial else loss['replacement']
    check('SITL MAVFTP loss ' + loss_case,
          loss['relay'] == loss_relay and loss_relay['case'] == loss_case and not loss_relay['errors'] and
          loss_relay['closed_by'] == 'client' and loss_relay['buffered_bytes_at_close'] == 0 and
          loss_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((loss_dir / n).read_bytes()).hexdigest() == digest for n,digest in loss_relay['capture_sha256'].items()) and
          all(hashlib.sha256((loss_dir / n).read_bytes()).hexdigest() == digest for n,digest in loss['hashes'].items()) and
          all(hashlib.sha256((root / 'mission-planner-portable' / n).read_bytes()).hexdigest() == digest for n,digest in loss['library_hashes'].items()) and
          (loss_dir / 'probe-exit.txt').read_text().strip() == '0' and
          loss['heartbeats'] and all(not(m['base_mode'] & 128) for m in loss['heartbeats']) and
          len(source_items) == len(loss['readback']) == 4 and loss['compared_fields'] == loss_fields and
          all(all(a[f] == b[f] for f in loss_fields) for a,b in zip(source_items,loss['readback'])) and
          all(line in (loss_dir / 'probe.log').read_text(encoding='utf8',errors='replace') for line in
              ('FTP_UPLOAD_RETURNED=True BYTES=162','MISSION_COUNT=4','DROP_PROBE_COMPLETE=True')) and
          ((is_partial and len(loss['dropped']) == 1 and loss['dropped'][0]['ftp']['opcode'] == 7 and
            loss['dropped'][0]['ftp']['offset'] == 80 and
            [m['ftp']['offset'] for m in loss['ftp_delivered'] if m['ftp']['opcode'] == 7] == [0,160] and
            any(m['ftp']['opcode'] == 128 and m['ftp']['request_opcode'] == 7 and m['ftp']['offset'] == 160 for m in loss['ftp_down'])) or
           (is_retry and len(loss['dropped']) == loss_relay['dropped_ftp_packets'] == 30 and
            all(m['ftp']['opcode'] == 128 and m['ftp']['request_opcode'] == 7 and m['ftp']['offset'] == 160 for m in loss['dropped']) and
            [m for m in loss['ftp_down_input'] if m['ftp']['opcode'] == 128 and m['ftp']['request_opcode'] == 7 and m['ftp']['offset'] == 160] == loss['dropped'] and
            not any(m['ftp']['opcode'] == 128 and m['ftp']['request_opcode'] == 7 and m['ftp']['offset'] == 160 for m in loss['ftp_down']) and
            sum(m['ftp']['opcode'] == 7 and m['ftp']['offset'] == 160 for m in loss['ftp_delivered']) == 30) or
           (not is_partial and not is_retry and not loss['dropped'])),
          'Disarmed source-built Copter SITL; relay fault cases and two failed injection attempts retained.')
ftp_rea = json.loads((root / 'mission-planner-binary-evidence/rea-ardupilot-all-members.json').read_text())['normalized_result']
ftp_methods = [m for m in ftp_rea['methods'] if m['declaring_type'] in ('MissionPlanner.ArduPilot.missionpck','MissionPlanner.ArduPilot.Mavlink.MAVFtp') and m['name'] in ('pack','unpack','GetFile','UploadFile')]
check('REA mission packer and MAVFTP method records',
      ftp_rea['artifact']['sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      {m['token'] for m in ftp_methods} == {'0x06000674','0x06000675','0x06000745','0x06000746','0x06000747'} and
      all(m['body']['status'] == 'present' and len(m['body']['il_sha256']) == 64 for m in ftp_methods),
      'REA method metadata and IL hashes; not proof of full UI or protocol behavior.')
fence_map = json.loads((root / 'mission-planner-binary-evidence/fence-method-map.json').read_text())
mavproxy_inv = json.loads((root / 'mission-planner-binary-evidence/mavproxy-source-inventory.json').read_text())
mavproxy_repo = root / 'ardupilot-mavproxy-source'
mavproxy_files_valid = True
for row in mavproxy_inv['files']:
    if row['status'] == 'not_checked_special_mode': continue
    p = mavproxy_repo / row['path']
    if not p.is_file(): mavproxy_files_valid = False; continue
    data = p.read_bytes()
    if row['status'] == 'crlf_normalized': data = data.replace(b'\r\n',b'\n')
    mavproxy_files_valid &= hashlib.sha1(('blob ' + str(len(data)) + '\0').encode()+data).hexdigest() == row['git_blob']
check('Pinned MAVProxy source inventory',
      mavproxy_inv['commit'] == '8258c223d8da58f2db71a1c2eabb6834f35e8d8c' and mavproxy_inv['tracked'] == len(mavproxy_inv['files']) == 477 and
      mavproxy_inv['counts'] == {'exact':87,'crlf_normalized':389,'mismatch':0,'missing':0,'not_checked_special_mode':1} and
      [r['path'] for r in mavproxy_inv['files'] if r['status'] == 'not_checked_special_mode'] == ['MAVProxy/modules/mavproxy_cesium'] and mavproxy_files_valid,
      'Regular file bytes checked against captured Git blob IDs, exact or CRLF-normalized; one submodule not checked.')
for proxy_case in ('mavproxy-sitl-smoke','mavproxy-sitl-smoke-2','mavproxy-sitl-smoke-3'):
    proxy_dir = root / 'sitl-evidence' / proxy_case
    proxy_summary = json.loads((proxy_dir / 'summary.json').read_text())
    proxy_result = json.loads((proxy_dir / 'result.json').read_text())
    proxy_log = (proxy_dir / 'mavproxy.log').read_text(encoding='utf8',errors='replace')
    check('MAVProxy source SITL ' + proxy_case,
          proxy_summary['result'] == proxy_result and not proxy_result['errors'] and proxy_result['source_commit'] == mavproxy_inv['commit'] and
          proxy_result['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          all(hashlib.sha256((proxy_dir / n).read_bytes()).hexdigest() == d for n,d in proxy_result['artifacts'].items()) and
          proxy_summary['source_inventory_sha256'] == hashlib.sha256((root / 'mission-planner-binary-evidence/mavproxy-source-inventory.json').read_bytes()).hexdigest() and
          proxy_summary['runner_source_sha256'] == hashlib.sha256((proxy_dir / 'runner-source.py').read_bytes()).hexdigest() and
          proxy_result['commands'] == ['param show LOG_DISARMED','wp list','exit'] and proxy_result['forwarded_datagrams'] > 0 and
          proxy_summary['heartbeat_count'] == len(proxy_summary['heartbeats']) > 0 and
          all(m['source'] == [1,1] and not(m['base_mode'] & 128) for m in proxy_summary['heartbeats']) and proxy_summary['bad_data_fragments'] == 0 and
          all(x in proxy_log for x in ('Detected vehicle 1:1 on link 0','Received 1431 parameters','LOG_DISARMED     0.0','Requesting 0 waypoints')) and
          ((proxy_case == 'mavproxy-sitl-smoke' and "Unknown command 'exit'" in proxy_log and proxy_result.get('forced_terminate')) or
           (proxy_case == 'mavproxy-sitl-smoke-2' and proxy_result.get('forced_terminate')) or
           (proxy_case == 'mavproxy-sitl-smoke-3' and proxy_result.get('stdin_closed') and not proxy_result.get('forced_terminate') and proxy_result['proxy_exit'] == 1)),
          'Pinned source, disarmed local SITL, parameter display and empty mission; first two termination attempts retained.')
for proxy_mission_case in ('mavproxy_mission_normal','mavproxy_mission_drop_ack','mavproxy_mission_normal_retry','mavproxy_mission_drop_ack_retry'):
    pm_dir = root / 'sitl-evidence' / ('command-ack-' + proxy_mission_case)
    pm = json.loads((pm_dir / 'summary.json').read_text())
    pm_relay = json.loads((pm_dir / 'relay-result.json').read_text())
    pm_probe = json.loads((pm_dir / 'mavproxy-result.json').read_text())
    pm_log = (pm_dir / 'mavproxy.log').read_text(encoding='utf8',errors='replace')
    pm_retry = proxy_mission_case.endswith('_retry')
    pm_drop = 'drop_ack' in proxy_mission_case
    pm_fields = ['seq','frame','command','param1','param2','param3','param4','x','y','z','mission_type']
    check('MAVProxy SITL mission ' + proxy_mission_case,
          pm['case'] == pm_probe['case'] == pm_relay['case'] == proxy_mission_case and pm['relay'] == pm_relay and pm['probe'] == pm_probe and
          pm_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          pm_probe['source_commit'] == mavproxy_inv['commit'] and
          all(hashlib.sha256((pm_dir / n).read_bytes()).hexdigest() == d for n,d in pm_relay['capture_sha256'].items()) and
          all(hashlib.sha256((pm_dir / n).read_bytes()).hexdigest() == d for n,d in pm_probe['artifacts'].items()) and
          pm['runner_sha256'] == hashlib.sha256((pm_dir / 'runner-source.py').read_bytes()).hexdigest() and
          pm['relay_source_sha256'] == hashlib.sha256((pm_dir / 'relay-source.py').read_bytes()).hexdigest() and
          pm['source_inventory_sha256'] == hashlib.sha256((root / 'mission-planner-binary-evidence/mavproxy-source-inventory.json').read_bytes()).hexdigest() and
          pm['heartbeats'] and all(not(m['base_mode'] & 128) for m in pm['heartbeats']) and
          ((not pm_retry and pm_probe['errors'] and 'MAVProxy did not report sending mission' in pm_probe['errors'][0] and
            pm_relay['errors'] and 'ConnectionResetError' in pm_relay['errors'][0] and 'usage: wp load FILENAME' in pm_log and not pm['uploads']) or
           (pm_retry and not pm_probe['errors'] and not pm_relay['errors'] and pm_relay['closed_by'] == 'client' and
            pm_probe['commands'] == ['wp load input.waypoints','exit'] and not pm_probe.get('forced_terminate') and pm_probe['proxy_exit'] == 1 and
            'Sent all 2 waypoints' in pm_log and [m['seq'] for m in pm['uploads']] == [0,1] and
            len(pm['acks']) == 1 and pm['acks'][0]['type'] == 0 and
            pm['compared_waypoint_fields'] == pm_fields and len(pm['readback']) == 2 and
            all(pm['uploads'][1][f] == pm['readback'][1][f] for f in pm_fields) and
            (pm['readback'][1]['x'],pm['readback'][1]['y'],pm['readback'][1]['z'],pm['readback'][1]['param1']) == (-353625000,1491660000,25,2) and
            ((pm_drop and pm_relay['dropped_mission_acks'] == 1 and pm['dropped'] == pm['acks'] and not pm['delivered_acks']) or
             (not pm_drop and not pm['dropped'] and pm['delivered_acks'] == pm['acks'])))),
          'Disarmed local SITL; normal or final-ACK loss and independent waypoint readback; earlier argument errors retained.')
for forwarding_case, expected_forward, expected_fwd, expected_disarmed in (
        ('default', True, 'true', 'true'), ('disabled', False, 'false', 'false'), ('disarmed', True, 'false', 'true')):
    fwd_dir = root / 'sitl-evidence' / ('command-ack-mavproxy_forward_' + forwarding_case)
    fwd = json.loads((fwd_dir / 'summary.json').read_text())
    fwd_relay = json.loads((fwd_dir / 'relay-result.json').read_text())
    fwd_probe = json.loads((fwd_dir / 'mavproxy-result.json').read_text())
    fwd_log = (fwd_dir / 'mavproxy.log').read_text(encoding='utf8',errors='replace')
    check('MAVProxy SITL downstream forwarding ' + forwarding_case,
          fwd['relay'] == fwd_relay and fwd['probe'] == fwd_probe and
          fwd_relay['case'] == fwd_probe['case'] == 'mavproxy_forward_' + forwarding_case and
          fwd_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          fwd_probe['source_commit'] == mavproxy_inv['commit'] and not fwd_probe['errors'] and fwd_probe['proxy_exit'] == 1 and not fwd_probe.get('forced_terminate') and
          fwd_probe['configured'] == {'mavfwd':expected_fwd,'mavfwd_disarmed':expected_disarmed} and
          ('mavfwd ' + expected_fwd.capitalize()) in fwd_log and ('mavfwd_disarmed ' + expected_disarmed.capitalize()) in fwd_log and
          all(hashlib.sha256((fwd_dir / n).read_bytes()).hexdigest() == d for n,d in fwd_relay['capture_sha256'].items()) and
          all(hashlib.sha256((fwd_dir / n).read_bytes()).hexdigest() == d for n,d in fwd_probe['artifacts'].items()) and
          fwd['runner_sha256'] == hashlib.sha256((fwd_dir / 'runner-source.py').read_bytes()).hexdigest() and
          fwd['relay_source_sha256'] == hashlib.sha256((fwd_dir / 'relay-source.py').read_bytes()).hexdigest() and
          fwd['source_inventory_sha256'] == hashlib.sha256((root / 'mission-planner-binary-evidence/mavproxy-source-inventory.json').read_bytes()).hexdigest() and
          fwd['request']['source'] == [211,77] and fwd['request']['param_id'] == 'LOG_DISARMED' and
          bytes.fromhex(fwd['request']['raw_hex']) == (fwd_dir / 'request.bin').read_bytes() and
          len(fwd['forwarded']) == len(fwd['responses']) == (1 if expected_forward else 0) and
          (not expected_forward or (fwd['forwarded'][0]['raw_hex'] == fwd['request']['raw_hex'] and fwd['responses'][0]['param_value'] == 0)) and
          fwd['heartbeats'] and all(m['source'] == [1,1] and not(m['base_mode'] & 128) for m in fwd['heartbeats']) and
          ((forwarding_case in ('default','disabled') and len(fwd_relay['errors']) == 1 and 'ConnectionResetError' in fwd_relay['errors'][0]) or
           (forwarding_case == 'disarmed' and not fwd_relay['errors'] and fwd_relay['closed_by'] == 'client')),
          'One disarmed SITL run; read-only downstream request, two relay reset observations retained; no physical vehicle.')
for armed_forward_mode in ('block','allow'):
  for armed_forward_retry in (False,True):
    armed_forward_case = 'mavproxy_forward_armed_' + armed_forward_mode + ('_retry' if armed_forward_retry else '')
    af_dir = root / 'sitl-evidence' / ('command-ack-' + armed_forward_case)
    af = json.loads((af_dir / 'summary.json').read_text())
    af_relay = json.loads((af_dir / 'relay-result.json').read_text())
    af_probe = json.loads((af_dir / 'mavproxy-result.json').read_text())
    af_expected = {'mavfwd':'false','mavfwd_disarmed':'true'} if armed_forward_mode == 'block' else {'mavfwd':'true','mavfwd_disarmed':'false'}
    check('MAVProxy SITL armed forwarding ' + armed_forward_case,
          af['relay'] == af_relay and af['probe'] == af_probe and af_relay['case'] == af_probe['case'] == armed_forward_case and
          af_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
          af_probe['source_commit'] == mavproxy_inv['commit'] and af_probe['configured'] == af_expected and
          all(hashlib.sha256((af_dir / n).read_bytes()).hexdigest() == d for n,d in af_relay['capture_sha256'].items()) and
          all(hashlib.sha256((af_dir / n).read_bytes()).hexdigest() == d for n,d in af_probe['artifacts'].items()) and
          af['runner_sha256'] == hashlib.sha256((af_dir / 'runner-source.py').read_bytes()).hexdigest() and
          af['relay_source_sha256'] == hashlib.sha256((af_dir / 'relay-source.py').read_bytes()).hexdigest() and
          af['source_inventory_sha256'] == hashlib.sha256((root / 'mission-planner-binary-evidence/mavproxy-source-inventory.json').read_bytes()).hexdigest() and
          af['commands'] and all(m['command'] == 400 and m['param2'] == 21196 for m in af['commands']) and
          ((not armed_forward_retry and af_probe['errors'] and 'heartbeat armed=True' in af_probe['errors'][0] and
            [m['param1'] for m in af['commands']] == [1] and any(m['result'] == 4 for m in af['acks']) and af['arm_notices'] and
            not any(m['base_mode'] & 128 for m in af['control_heartbeats']) and not af['forwarded'] and not af['replies']) or
           (armed_forward_retry and not af_probe['errors'] and af_probe['proxy_exit'] == 1 and not af_probe.get('forced_terminate') and
            [m['param1'] for m in af['commands']] == [1,0] and [m['result'] for m in af['acks']] == [0,0] and
            bool(af_probe['armed_heartbeat']['base_mode'] & 128) and not(af_probe['final_heartbeat']['base_mode'] & 128) and
            af['armed_output_heartbeats'] and any(m['base_mode'] & 128 for m in af['armed_output_heartbeats']) and
            af['request_window_heartbeats'] and all(m['base_mode'] & 128 for m in af['request_window_heartbeats']) and
            len(af['forwarded']) == len(af['replies']) == (1 if armed_forward_mode == 'allow' else 0) and
            (armed_forward_mode == 'block' or (bytes.fromhex(af['forwarded'][0]['raw_hex']) == (af_dir / 'request.bin').read_bytes() and af['replies'][0]['param_value'] == 0)))),
          'Disposable SITL only; initial arm rejection or forced simulated arm and confirmed disarm; read-only downstream request.')
pm_reject_dir = root / 'sitl-evidence/command-ack-mavproxy_mission_reject'
pm_reject = json.loads((pm_reject_dir / 'summary.json').read_text())
pm_reject_relay = json.loads((pm_reject_dir / 'relay-result.json').read_text())
pm_reject_probe = json.loads((pm_reject_dir / 'mavproxy-result.json').read_text())
pm_reject_log = (pm_reject_dir / 'mavproxy.log').read_text(encoding='utf8',errors='replace')
pm_reject_fields = ['seq','frame','command','param1','param2','param3','param4','x','y','z','mission_type']
check('MAVProxy SITL rejected mission replacement',
      pm_reject['relay'] == pm_reject_relay and pm_reject['probe'] == pm_reject_probe and
      pm_reject_relay['case'] == pm_reject_probe['case'] == 'mavproxy_mission_reject' and
      not pm_reject_relay['errors'] and not pm_reject_probe['errors'] and pm_reject_relay['closed_by'] == 'client' and
      pm_reject_relay['binary_sha256'] == hashlib.sha256((root / 'sitl-evidence/archive-built/arducopter').read_bytes()).hexdigest() and
      pm_reject_probe['source_commit'] == mavproxy_inv['commit'] and
      all(hashlib.sha256((pm_reject_dir / n).read_bytes()).hexdigest() == d for n,d in pm_reject_relay['capture_sha256'].items()) and
      all(hashlib.sha256((pm_reject_dir / n).read_bytes()).hexdigest() == d for n,d in pm_reject_probe['artifacts'].items()) and
      pm_reject['runner_sha256'] == hashlib.sha256((pm_reject_dir / 'runner-source.py').read_bytes()).hexdigest() and
      pm_reject['relay_source_sha256'] == hashlib.sha256((pm_reject_dir / 'relay-source.py').read_bytes()).hexdigest() and
      pm_reject['source_inventory_sha256'] == hashlib.sha256((root / 'mission-planner-binary-evidence/mavproxy-source-inventory.json').read_bytes()).hexdigest() and
      pm_reject['heartbeats'] and all(not(m['base_mode'] & 128) for m in pm_reject['heartbeats']) and
      [m['command'] for m in pm_reject['uploads']] == [16,16,16,65535] and [m['type'] for m in pm_reject['acks']] == [0,3] and
      pm_reject['compared_fields'] == pm_reject_fields and len(pm_reject['baseline_readback']) == len(pm_reject['after_readback']) == 2 and
      all(all(a[f] == b[f] for f in pm_reject_fields) for a,b in zip(pm_reject['baseline_readback'],pm_reject['after_readback'])) and
      (pm_reject['after_readback'][1]['command'],pm_reject['after_readback'][1]['x'],pm_reject['after_readback'][1]['y'],pm_reject['after_readback'][1]['z']) == (16,-353625000,1491660000,25) and
      pm_reject_log.count('Sent all 2 waypoints') == 2 and 'Got MISSION_ACK: TYPE_MISSION: ACCEPTED' in pm_reject_log and
      pm_reject_log.rfind('Sent all 2 waypoints') < pm_reject_log.rfind('Got MISSION_ACK: TYPE_MISSION: UNSUPPORTED') and
      pm_reject_probe['commands'] == ['wp load baseline.waypoints','wp load invalid.waypoints','exit'] and pm_reject_probe['proxy_exit'] == 1 and not pm_reject_probe.get('forced_terminate'),
      'One disarmed SITL rejection; MAVProxy reported sent then unsupported, independent readback matched selected baseline fields.')
fence_map_valid = len(fence_map['groups']) == 2
for group in fence_map['groups']:
    group_index, group_assembly = root / group['index_path'], root / group['assembly_path']
    fence_map_valid = fence_map_valid and group['index_sha256'] == hashlib.sha256(group_index.read_bytes()).hexdigest() and group['assembly_sha256'] == hashlib.sha256(group_assembly.read_bytes()).hexdigest()
    with sqlite3.connect(f'file:{group_index.as_posix()}?mode=ro', uri=True) as connection:
        for method in group['methods']:
            if group_assembly.name == 'MissionPlanner.exe':
                row = connection.execute('select declaring_type,name,il_sha256,body_status from methods where token=?', (method['token'],)).fetchone()
                calls = connection.execute('select il_offset,opcode,target_name,target_declaring_type from calls where caller_token=? order by il_offset', (method['token'],))
            else:
                row = connection.execute('select declaring_type,name,il_sha256,body_status from methods where assembly=? and token=?', (group_assembly.name, method['token'])).fetchone()
                calls = connection.execute('select il_offset,opcode,target_name,target_declaring_type from calls where assembly=? and caller_token=? order by il_offset', (group_assembly.name, method['token']))
            fence_map_valid = fence_map_valid and row == (method['declaring_type'], method['name'], method['il_sha256'], method['body_status']) and \
                [dict(zip(('il_offset', 'opcode', 'name', 'type'), call)) for call in calls] == method['calls']
check('REA selected fence method records', fence_map_valid and [len(g['methods']) for g in fence_map['groups']] == [7, 5],
      'Static distributed assembly identities and call references only; no UI behavior inferred.')
terrain_map = json.loads((root / 'mission-planner-binary-evidence/terrain-method-map.json').read_text())
terrain_index = root / 'mission-planner-binary-evidence/rea-supporting-index.sqlite'
with sqlite3.connect(f'file:{terrain_index.as_posix()}?mode=ro', uri=True) as connection:
    terrain_rows = {m['token']: connection.execute('select declaring_type,name,il_sha256,body_status from methods where assembly=? and token=?',
        ('MissionPlanner.Utilities.dll', m['token'])).fetchone() for m in terrain_map['methods']}
    terrain_calls = {m['token']: [dict(zip(('il_offset', 'opcode', 'name', 'type'), row)) for row in connection.execute(
        'select il_offset,opcode,target_name,target_declaring_type from calls where assembly=? and caller_token=? order by il_offset',
        ('MissionPlanner.Utilities.dll', m['token']))] for m in terrain_map['methods']}
check('REA terrain responder method records', terrain_map['assembly_sha256'] ==
      hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() and
      terrain_map['index_sha256'] == hashlib.sha256(terrain_index.read_bytes()).hexdigest() and
      [m['token'] for m in terrain_map['methods']] == ['0x06000715', '0x06000718', '0x06000719', '0x0600071a', '0x0600071b'] and
      all(terrain_rows[m['token']] == (m['declaring_type'], m['name'], m['il_sha256'], m['body_status']) and
          terrain_calls[m['token']] == m['calls'] for m in terrain_map['methods']),
      'Static REA records for distributed Utilities; runtime test uses modified Utilities.')
accel_map = json.loads((root / 'mission-planner-binary-evidence/accel-calibration-method-map.json').read_text())
accel_index = root / 'mission-planner-binary-evidence/rea-main-index.sqlite'
with sqlite3.connect(f'file:{accel_index.as_posix()}?mode=ro', uri=True) as connection:
    accel_rows = {m['token']: connection.execute('select declaring_type,name,il_sha256,body_status from methods where token=?', (m['token'],)).fetchone() for m in accel_map['methods']}
    accel_calls = {m['token']: [dict(zip(('il_offset', 'opcode', 'target_token', 'name', 'type'), row)) for row in connection.execute(
        'select il_offset,opcode,target_token,target_name,target_declaring_type from calls where caller_token=? order by il_offset', (m['token'],))] for m in accel_map['methods']}
check('REA accelerometer calibration method records',
      accel_map['assembly_sha256'] == hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.exe').read_bytes()).hexdigest() and
      accel_map['index_sha256'] == hashlib.sha256(accel_index.read_bytes()).hexdigest() and
      [m['token'] for m in accel_map['methods']] == ['0x06000d3a', '0x06000d3b', '0x06000d3d', '0x06000d3e'] and
      all(accel_rows[m['token']] == (m['declaring_type'], m['name'], m['il_sha256'], m['body_status']) and
          accel_calls[m['token']] == m['calls'] for m in accel_map['methods']) and
      {'sendPacket', 'doCommand', 'SubscribeToPacketType'} <= {call['name'] for call in accel_map['methods'][0]['calls']} and
      'UnSubscribeToPacketType' in {call['name'] for call in accel_map['methods'][1]['calls']},
      'Static REA method and call records only; no UI execution claim.')
translation_log = (root / 'sitl-evidence/mode-translation-synthetic/probe.log').read_text(encoding='utf-16').splitlines()
check('synthetic tracker mode translation', translation_log == [
    'NAME=SCAN RESULT=True TARGET=1 BASE=1 CUSTOM=2', 'NAME=scan RESULT=True TARGET=1 BASE=1 CUSTOM=2',
    'NAME=not-a-mode RESULT=False TARGET=1 BASE=0 CUSTOM=0', 'NAME=<empty> RESULT=False TARGET=1 BASE=0 CUSTOM=0',
    'NAME=<null> RESULT=False TARGET=1 BASE=0 CUSTOM=0', 'STALE_INPUT RESULT=True TARGET=1 BASE=1 CUSTOM=2'],
    'Tracker mode list, direct in-memory method call; fresh structure used by ordinary string setter.')
string_mode_dir = root / 'sitl-evidence/mode-translation-synthetic'
string_mode = json.loads((string_mode_dir / 'string-send-summary.json').read_text())
string_mode_bytes = (string_mode_dir / 'string-send.bin').read_bytes()
string_mode_log = (string_mode_dir / 'string-send.log').read_text(encoding='utf-16').splitlines()
check('synthetic tracker string mode send',
      hashlib.sha256(string_mode_bytes).hexdigest() == string_mode['capture_sha256'] and
      len(string_mode_bytes) == string_mode['bytes'] and string_mode_log == string_mode['log_lines'] ==
      ['INVALID_BYTES=0', 'VALID_BYTES=' + str(len(string_mode_bytes))] and
      [m['mavpackettype'] for m in string_mode['frames']] == ['COMMAND_LONG', 'SET_MODE', 'SET_MODE'] and
      string_mode['frames'][0]['command'] == 176 and string_mode['frames'][0]['target_system'] == 1 and
      string_mode['frames'][0]['target_component'] == 1 and string_mode['frames'][0]['param1'] == 1 and
      string_mode['frames'][0]['param2'] == 2 and
      all(m['target_system'] == 1 and m['base_mode'] == 1 and m['custom_mode'] == 2 for m in string_mode['frames'][1:]),
      'In-memory tracker string setter; no vehicle, Copter metadata, or UI behavior claim.')
mode_map = json.loads((root / 'mission-planner-binary-evidence/flight-mode-method-map.json').read_text())
mode_index = root / 'mission-planner-binary-evidence/rea-supporting-index.sqlite'
with sqlite3.connect(f'file:{mode_index.as_posix()}?mode=ro', uri=True) as connection:
    mode_rows = {row[0]: row[1:] for row in connection.execute(
        'SELECT token,declaring_type,name,il_sha256,body_status FROM methods WHERE assembly=?', ('MissionPlanner.ArduPilot.dll',))}
    mode_calls = {m['token']: [dict(zip(('il_offset', 'opcode', 'name', 'type'), row)) for row in connection.execute(
        'SELECT il_offset,opcode,target_name,target_declaring_type FROM calls WHERE assembly=? AND caller_token=? ORDER BY il_offset',
        ('MissionPlanner.ArduPilot.dll', m['token']))] for m in mode_map['methods']}
check('REA flight mode method records', mode_map['assembly_sha256'] ==
      hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest() and
      mode_map['index_sha256'] == hashlib.sha256(mode_index.read_bytes()).hexdigest() and
      [m['token'] for m in mode_map['methods']] == ['0x06000490', '0x06000491', '0x06000492', '0x06000493', '0x060004ae', '0x060004af'] and
      all(mode_rows[m['token']] == (m['declaring_type'], m['name'], m['il_sha256'], m['body_status']) and
          mode_calls[m['token']] == m['calls'] for m in mode_map['methods']),
      'Static build-local REA records; no runtime dispatch claim.')
guided_dir = root / 'sitl-evidence/command-ack-guided_position'
check('REA guided position method records',
      [mode_rows[t] for t in ('0x06000487', '0x06000488', '0x0600048b')] == [
          ('MissionPlanner.MAVLinkInterface', 'setGuidedModeWP', '9f186a36bd900703a7dcba7affcf40bd4f4f0165a43c19fb265a626771116a21', 'present'),
          ('MissionPlanner.MAVLinkInterface', 'setGuidedModeWP', 'e9f5495c18dc274bd032f1f11992239e2b9d077d624e0f427c3419603157865f', 'present'),
          ('MissionPlanner.MAVLinkInterface', 'setPositionTargetGlobalInt', 'a00cb9cf934ce31c2885d138d9d62c0830517c46fc0b75896edb46c223734862', 'present')],
      'Static REA records for the pinned assembly, not UI execution.')
guided = json.loads((guided_dir / 'guided-summary.json').read_text())
guided_relay = json.loads((guided_dir / 'relay-result.json').read_text())
guided_raw_hash = hashlib.sha256((guided_dir / 'to_sitl_output.bin').read_bytes()).hexdigest()
check('guided position disarmed packet capture',
      guided_raw_hash == guided['capture_sha256'] == guided_relay['capture_sha256']['to_sitl_output.bin'] and
      not guided_relay['errors'] and guided['probe_exit'] == 0 and
      (guided_dir / 'probe-exit.txt').read_text().strip() == '0' and
      guided['target_packet_indices'][0] < min(guided['set_mode_packet_indices']) < guided['target_packet_indices'][1] and
      [(x['lat_int'], x['lon_int'], x['alt'], x['coordinate_frame'], x['type_mask']) for x in guided['targets']] ==
      [(-353631000, 1491651000, 11.0, 6, 65016), (-353632000, 1491652000, 12.0, 6, 65016)],
      'Disarmed simulator and packet capture; target acceptance and flight not observed.')
flight_dir = root / 'sitl-evidence/command-ack-guided_flight_retry'
flight = json.loads((flight_dir / 'guided-flight-summary.json').read_text())
flight_relay = json.loads((flight_dir / 'relay-result.json').read_text())
check('guided position airborne SITL capture',
      all(hashlib.sha256((flight_dir / name).read_bytes()).hexdigest() == flight_relay['capture_sha256'][name] == flight[key]
          for name, key in [('to_sitl_output.bin', 'outbound_sha256'), ('to_client_output.bin', 'inbound_sha256')]) and
      not flight_relay['errors'] and flight['probe_exit'] == 0 and (flight_dir / 'probe-exit.txt').read_text().strip() == '0' and
      flight['target']['lat_int'] == -353631809 and flight['target']['lon_int'] == 1491652298 and
      flight['target']['alt'] == 5 and flight['peak_relative_altitude_m'] >= 3.5 and
      flight['closest_airborne_distance_m'] < 2.5 and flight['final_heartbeat']['custom_mode'] == 9 and
      not (flight['final_heartbeat']['base_mode'] & 128),
      'One disposable source-built Copter simulation; no UI or physical aircraft.')
plane_dir = root / 'sitl-evidence/command-ack-plane_guided'
plane = json.loads((plane_dir / 'plane-guided-summary.json').read_text())
plane_relay = json.loads((plane_dir / 'relay-result.json').read_text())
check('Plane guided mission item and acknowledgment capture',
      all(hashlib.sha256((plane_dir / name).read_bytes()).hexdigest() == plane_relay['capture_sha256'][name] == plane[key]
          for name, key in [('to_sitl_output.bin', 'outbound_sha256'), ('to_client_output.bin', 'inbound_sha256')]) and
      not plane_relay['errors'] and plane['probe_exit'] == 0 and (plane_dir / 'probe-exit.txt').read_text().strip() == '0' and
      [m['type'] for m in plane['mission_acks']] == [1, 0] and
      len(plane['mission_items']) == 2 and all(m['mavpackettype'] == 'MISSION_ITEM' and m['current'] == 2 and
      m['frame'] == 3 and m['command'] == 16 for m in plane['mission_items']) and
      plane['manual_error_logged_but_call_returned'] and
      plane['mission_item_indices'][0] < min(plane['mode_indices']) < plane['mission_item_indices'][1],
      'One disarmed source-built Plane run; no aircraft movement or UI claim.')
for case, expected_items, expected_delivered, timeout, expected_state in [
        ('plane_guided_drop_one', 2, 1, False, ['-353632011', '1491652069', '22']),
        ('plane_guided_drop_all', 11, 0, True, ['0', '0', '0'])]:
    loss_dir = root / ('sitl-evidence/command-ack-' + case)
    loss = json.loads((loss_dir / 'loss-summary.json').read_text())
    loss_relay = json.loads((loss_dir / 'relay-result.json').read_text())
    check('Plane guided ACK loss ' + case,
          all(hashlib.sha256((loss_dir / name).read_bytes()).hexdigest() == digest == loss_relay['capture_sha256'][name]
              for name, digest in loss['hashes'].items()) and not loss_relay['errors'] and
          loss['sent_items'] == loss['simulator_accepted_acks'] == expected_items and
          loss['dropped_acks'] == loss_relay['dropped_mission_acks'] == expected_items - expected_delivered and
          loss['delivered_acks'] == expected_delivered and loss['timeout_logged'] == timeout and
          loss['returned_to_caller'] and loss['guided_state_after'] == expected_state and
          (loss_dir / 'probe-exit.txt').read_text().strip() == '0',
          'Disarmed source-built Plane; withheld mission ACKs, not flight or UI.')
state_dir = root / 'sitl-evidence/command-ack-plane_guided_state'
state = json.loads((state_dir / 'state-summary.json').read_text())
state_relay = json.loads((state_dir / 'relay-result.json').read_text())
check('Plane rejected guided target cache and mission readback',
      all(hashlib.sha256((state_dir / name).read_bytes()).hexdigest() == state_relay['capture_sha256'][name] == state[key]
          for name, key in [('to_sitl_output.bin', 'outbound_sha256'), ('to_client_output.bin', 'inbound_sha256')]) and
      not state_relay['errors'] and state['probe_exit'] == 0 and (state_dir / 'probe-exit.txt').read_text().strip() == '0' and
      state['ack_results'] == [0, 1, 0] and state['mission_counts'] == [2, 2, 2] and
      len(state['readback_items']) == 3 and all((m['seq'], m['x'], m['y'], m['z']) == (1, -353630000, 1491655000, 20)
                                              for m in state['readback_items']) and
      state['cache_after_rejection'] == [-353630981, 1491651000, 21] and
      state['cache_after_acceptance'] == [-353632011, 1491652069, 22],
      'Disarmed Plane; count and one mission item observed, not full mission or UI.')
edges_dir = root / 'sitl-evidence/waypoint-import-edges'
edges = json.loads((edges_dir / 'summary.json').read_text())
edges_log = (edges_dir / 'probe.log').read_text().replace('\r', '')
with sqlite3.connect(f'file:{mode_index.as_posix()}?mode=ro', uri=True) as connection:
    edges_method = connection.execute('select declaring_type,name,il_sha256,body_status from methods where assembly=? and token=?',
                                      ('MissionPlanner.Utilities.dll', edges['rea_method_token'])).fetchone()
check('synthetic WPL import edge cases',
      all(hashlib.sha256((edges_dir / name).read_bytes()).hexdigest() == digest for name, digest in edges['fixture_hashes'].items()) and
      hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest() == edges['utilities_sha256'] and
      edges_method == ('MissionPlanner.Utilities.WaypointFile', 'ReadWaypointFile', edges['rea_il_sha256'], 'present') and
      edges['probe_exit'] == 0 and (edges_dir / 'probe-exit.txt').read_text().strip() == '0' and
      all(line in edges_log for line in ['short_row COUNT=2', 'duplicate_sequence COUNT=3',
          'nonfinite ITEM=1 ID=16 FRAME=3 LAT=NaN LON=149.1651 ALT=21', 'loose_header COUNT=2', 'gap_sequence COUNT=2']),
      'Synthetic library import; no GUI or vehicle validation claim.')
support = json.loads((root / 'supportproxy-evidence/summary.json').read_text())
support_repo = root / 'supportproxy-source'
check('SupportProxy source-built local tests',
      support['revisions'] == {'supportproxy':'21ca25286b2a0bcc25228e4d6bc20c5438abdcce',
          'mavlink':'a23652e3c7d1d7a94b1c2d354a13ce4858cd0996', 'pymavlink':'19880422d451de4daba3fd96781076afb1cb889c'} and
      hashlib.sha256((support_repo/'supportproxy').read_bytes()).hexdigest() == support['binary_sha256'] and
      all(hashlib.sha256((support_repo/name).read_bytes()).hexdigest() == digest for name, digest in support['source_sha256'].items()) and
      hashlib.sha256((root/'research-tools/supportproxy-loopback-bind.c').read_bytes()).hexdigest() == support['interposer_source_sha256'] and
      hashlib.sha256((root/'supportproxy-deps/loopback-bind.so').read_bytes()).hexdigest() == support['interposer_binary_sha256'] and
      all(hashlib.sha256((root/'supportproxy-evidence'/name/'pytest.log').read_bytes()).hexdigest() == row['log_sha256'] and
          row['expected_summary'] in (root/'supportproxy-evidence'/name/'pytest.log').read_text() and
          (root/'supportproxy-evidence'/name/'exit.txt').read_text().strip() == '0' for name,row in support['tests'].items()),
      'Selected upstream tests with loopback bind interposer; no SITL, UI or remote network claim.')
for form in ('int', 'float'):
    nan_dir = root / ('sitl-evidence/command-ack-wpl_nan_' + form)
    nan_summary = json.loads((nan_dir / 'nan-summary.json').read_text())
    nan_log = (nan_dir / 'probe.log').read_text(errors='replace')
    check('WPL NaN upload observation ' + form,
          all(hashlib.sha256((nan_dir / name).read_bytes()).hexdigest() == digest for name, digest in nan_summary['files'].items()) and
          nan_summary['form'] == form and nan_summary['item_count'] >= 1 and
          ('BASELINE_ITEM1=-35.363,149.1655,20' in nan_log) and
          ((form == 'int' and nan_summary['sent_item']['x'] == -2147483648 and 10 in nan_summary['ack_types'] and
            nan_summary['post_upload_readback_completed'] and 'AFTER_ITEM1=-35.363,149.1655,20' in nan_log and nan_summary['probe_exit'] == 0) or
           (form == 'float' and nan_summary['sent_item']['x'] == 'NaN' and nan_summary['relay_closed_by'] == 'sitl' and
            not nan_summary['post_upload_readback_completed'] and nan_summary['probe_exit'] == 1 and
            'ERROR: Floating point exception - aborting' in (nan_dir/'sitl.log').read_text(errors='replace'))),
          'Saved simulator observations; failure cause and physical behavior unproven.')
out = root / 'research-evidence-verification.json'
out.write_text(json.dumps({'checks': checks, 'passed': all(c['passed'] for c in checks)}, indent=2) + '\n')
for c in checks:
    print(('PASS' if c['passed'] else 'FAIL') + ' ' + c['name'])
if not all(c['passed'] for c in checks):
    raise SystemExit(1)
