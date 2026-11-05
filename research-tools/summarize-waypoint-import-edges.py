from pathlib import Path
import hashlib, json, sqlite3
root = Path(__file__).resolve().parent.parent
run = root/'sitl-evidence/waypoint-import-edges'
log = (run/'probe.log').read_text().replace('\r','')
for s in ['short_row COUNT=2', 'short_row ITEM=1 ID=16 FRAME=3 LAT=-35.3632 LON=149.1652 ALT=22',
          'duplicate_sequence COUNT=3', 'duplicate_sequence ITEM=2 ID=16 FRAME=3 LAT=-35.3631 LON=149.1651 ALT=23',
          'nonfinite ITEM=1 ID=16 FRAME=3 LAT=NaN LON=149.1651 ALT=21', 'loose_header COUNT=2',
          'gap_sequence COUNT=2', 'gap_sequence ITEM=1 ID=16 FRAME=3 LAT=-35.3632 LON=149.1652 ALT=22']:
    assert s in log, s
assert (run/'probe-exit.txt').read_text().strip() == '0'
with sqlite3.connect(root/'mission-planner-binary-evidence/rea-supporting-index.sqlite') as c:
    row = c.execute('select declaring_type,name,il_sha256,body_status from methods where assembly=? and token=?',
                    ('MissionPlanner.Utilities.dll','0x060005ce')).fetchone()
assert row == ('MissionPlanner.Utilities.WaypointFile', 'ReadWaypointFile', '6e5c384b378854c093386d3af4e52bbb82c24cebdce58f18dca7996b13a9e6b8', 'present')
names = ['short_row.waypoints','duplicate_sequence.waypoints','nonfinite.waypoints','loose_header.waypoints',
         'gap_sequence.waypoints','probe.log','probe-source.cs','probe.exe']
summary = {'scope':'synthetic files and original distributed Utilities library; no UI or vehicle',
           'fixture_hashes':{n:hashlib.sha256((run/n).read_bytes()).hexdigest() for n in names},
           'utilities_sha256':hashlib.sha256((root/'mission-planner-portable/MissionPlanner.Utilities.dll').read_bytes()).hexdigest(),
           'rea_method_token':'0x060005ce', 'rea_il_sha256':row[2], 'probe_exit':0}
(run/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
