from pathlib import Path
import json, ntpath, os
root = Path(__file__).resolve().parent.parent
stage = root/'mission-planner-rea-upload'
manifest = json.loads((stage/'UPLOAD-MANIFEST.json').read_text())
for row in manifest['errors']:
    rel = row['path']
    if 'WinError 183' not in row['error']: continue
    candidate = stage/Path(rel)
    if ntpath.commonpath([str(stage),str(candidate)]) != str(stage): raise ValueError('outside staging')
    os.unlink('\\\\?\\'+str(candidate))
    print('removed staged WSL link:', rel)
