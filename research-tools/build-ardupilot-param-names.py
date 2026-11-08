"""Write coverage/ardupilot-param-names.csv: every parameter name the pinned ArduPilot snapshot declares, per vehicle.

Input is the `apm.pdef.json` files that the snapshot's own generator writes, one directory per vehicle:

    # in WSL, once per vehicle, from an empty working directory (needs a Python with lxml, e.g. ~/venv-ap)
    PYTHONDONTWRITEBYTECODE=1 python3 <ardupilot>/Tools/autotest/param_metadata/param_parse.py --vehicle ArduCopter --format json

    python research-tools/build-ardupilot-param-names.py <dir containing ArduCopter/apm.pdef.json, ArduPlane/...>

Only names are kept (no descriptions or ranges). Limits: the generator documents parameters found by static parsing of the
source; parameters created at run time (for example per-instance prefixes it does not expand) can be missing.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'coverage/ardupilot-param-names.csv'
VEHICLES = ['ArduCopter', 'ArduPlane', 'Rover', 'ArduSub', 'AntennaTracker', 'Blimp']


def names_in(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    return {name for group in data.values() if isinstance(group, dict) for name in group}


def main():
    src = Path(sys.argv[1])
    per = {v: names_in(src / v / 'apm.pdef.json') for v in VEHICLES}
    every = sorted(set().union(*per.values()))
    with OUT.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['name'] + VEHICLES)
        for n in every:
            w.writerow([n] + [1 if n in per[v] else 0 for v in VEHICLES])
    print(len(every), 'names;', ', '.join(f'{v} {len(per[v])}' for v in VEHICLES), '->', OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
