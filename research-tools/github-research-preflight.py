"""Inventory research files before publishing; do not print file contents."""
from pathlib import Path
import json, os
root = Path(__file__).resolve().parent.parent
items = [p for p in root.iterdir() if p.is_file() and (p.name.endswith('-Trace.md') or p.name in (
    'Reverse-Engineering-Coverage.md','ArduPilot-Organization-Inventory.md','ArduPilot-Source-Map.md',
    'Mission-Planner-Investigation.md','Mission-Planner-Managed-References.md','Mission-Planner-Screen-Map.md',
    'Mission-Planner-UI-Observations.md','research-evidence-verification.json'))]
names = ['ardupilot-mavproxy-source','ardupilot-source','mission-planner-1.3.83-source',
         'mission-planner-binary-evidence','mission-planner-isolated','mission-planner-portable',
         'mission-planner-research','mission-planner-runtime','research-tools','sitl-evidence',
         'supportproxy-deps','supportproxy-evidence','supportproxy-source']
items += [root/n for n in names if (root/n).exists()]
skip_dirs = {'.git','node_modules','__pycache__','.pytest_cache'}
result = {'groups':{},'oversized':[], 'sensitive_names':[], 'skipped_directories':{}}
for item in items:
    total = count = 0
    if item.is_file(): files = [item]
    else:
        files = []
        for directory, dirs, filenames in os.walk(item):
            for d in list(dirs):
                if d in skip_dirs:
                    result['skipped_directories'][d] = result['skipped_directories'].get(d,0)+1
                    dirs.remove(d)
            files.extend(Path(directory)/name for name in filenames)
    for f in files:
        try:
            if f.is_symlink(): continue
            size = f.stat().st_size; total += size; count += 1
            rel = f.relative_to(root).as_posix()
            if size >= 100_000_000: result['oversized'].append({'path':rel,'bytes':size})
            name = f.name.lower()
            if any(s in name for s in ('credential','secret','private_key','id_rsa','.env','token','password')):
                result['sensitive_names'].append(rel)
        except OSError: pass
    result['groups'][item.name] = {'files':count,'bytes':total}
out = root/'github-research-preflight.json'
out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':sum(x['files'] for x in result['groups'].values()),
                  'bytes':sum(x['bytes'] for x in result['groups'].values()),
                  'oversized':result['oversized'], 'sensitive_name_count':len(result['sensitive_names']),
                  'groups':result['groups'],'skipped_directories':result['skipped_directories']},indent=2))
