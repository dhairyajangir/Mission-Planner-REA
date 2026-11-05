"""Compare message-name counts, without claiming field-by-field equivalence."""
from collections import Counter
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
reference = json.loads((root / 'download-verification.json').read_text())
converted = root / 'converted.log'
with converted.open(encoding='ascii', errors='replace') as stream:
    counts = Counter(line.split(',', 1)[0] for line in stream)
keys = sorted(set(counts) | set(reference['message_types']))
differences = {key: {'pymavlink': reference['message_types'].get(key, 0), 'mission_planner': counts.get(key, 0)}
               for key in keys if reference['message_types'].get(key, 0) != counts.get(key, 0)}
transcript = (root / 'conversion-attempt.log').read_text(errors='replace')
result = {'conversion_bytes': converted.stat().st_size,
          'conversion_sha256': hashlib.sha256(converted.read_bytes()).hexdigest(),
          'conversion_lines': sum(counts.values()), 'pymavlink_messages': reference['message_count'],
          'message_type_count_differences': differences,
          'converter_reported_bad_binary_line': 'Bad Binary log line' in transcript,
          'scope': 'Name counts only; does not compare record values or identify cause of difference.'}
(root / 'conversion-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
