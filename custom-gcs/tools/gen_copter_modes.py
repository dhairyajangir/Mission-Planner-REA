"""Write customgcs/data/copter_modes.json from ArduCopter/mode.h (the `enum class Number` of flight modes) of a supplied ArduPilot tree.

    python3 gen_copter_modes.py <ardupilot tree> [output file]

Only the numbers and names in the enum are taken; AUTO_RTL (27) is "not a true mode" per its source comment (AUTO reports it) and is flagged so it is not offered as a target.
"""
import json
import os
import re
import sys

tree = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'customgcs', 'data', 'copter_modes.json')
text = open(os.path.join(tree, 'ArduCopter', 'mode.h'), encoding='utf-8').read()
body = re.search(r'enum class Number : uint8_t \{(.*?)\n    \};', text, re.S).group(1)
modes = {}
for m in re.finditer(r'^\s*([A-Z_]+)\s*=\s*(\d+),\s*(?://\s*(.*))?$', body, re.M):
    modes[m.group(1)] = {'number': int(m.group(2)), 'comment': (m.group(3) or '').strip(), 'settable': not (m.group(1) == 'AUTO_RTL')}
json.dump({'source': 'ArduCopter/mode.h enum class Number', 'modes': modes}, open(out, 'w'), indent=1, sort_keys=True)
print(len(modes), 'modes written to', out)
