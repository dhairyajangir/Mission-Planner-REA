"""Write a flight-mode table from `enum class Number` in <vehicle>/mode.h of a supplied ArduPilot tree.

    python3 gen_copter_modes.py <ardupilot tree> [vehicle dir, default ArduCopter] [output file]

With ArduCopter this writes customgcs/data/copter_modes.json, with Rover customgcs/data/rover_modes.json, with ArduPlane customgcs/data/plane_modes.json (the file name is kept from the first version, which only did Copter).
Numbers, names and comments are taken from the enum; entries inside an #if (nested ones are joined with &&) are flagged "conditional" (compiled only when that option is on); AUTO_RTL ("not a true mode") and
INITIALISING (the state while starting) are flagged not settable so they are never offered as a target.
"""
import json
import os
import re
import sys

tree = sys.argv[1]
vehicle = sys.argv[2] if len(sys.argv) > 2 else 'ArduCopter'
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'customgcs', 'data')
out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(data_dir, {'ArduCopter': 'copter_modes.json', 'Rover': 'rover_modes.json', 'ArduPlane': 'plane_modes.json'}.get(vehicle, vehicle.lower() + '_modes.json'))
text = open(os.path.join(tree, vehicle, 'mode.h'), encoding='utf-8').read()
body = re.search(r'enum (?:class )?Number : uint8_t \{(.*?)\n    \};', text, re.S).group(1)       # Rover and Copter use `enum class`, Plane a plain `enum`
NOT_SETTABLE = ('AUTO_RTL', 'INITIALISING')
modes, conditions = {}, []
for line in body.splitlines():
    stripped = line.strip()
    if stripped.startswith('#if'):
        conditions.append(stripped[3:].strip())            # nested #if blocks stack up
        continue
    if stripped.startswith('#endif'):
        if conditions:
            conditions.pop()
        continue
    m = re.match(r'([A-Z_0-9]+)\s*=\s*(\d+),\s*(?://\s*(.*))?$', stripped)
    if m:
        modes[m.group(1)] = {'number': int(m.group(2)), 'comment': (m.group(3) or '').strip(), 'settable': m.group(1) not in NOT_SETTABLE, 'conditional': ' && '.join(conditions) or None}
json.dump({'source': '%s/mode.h enum class Number' % vehicle, 'modes': modes}, open(out, 'w'), indent=1, sort_keys=True)
print(len(modes), 'modes written to', out)
