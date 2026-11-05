"""Create a hard-linked snapshot of the Mission Planner research for Git upload."""
from pathlib import Path
import json, os, shutil
root = Path(__file__).resolve().parent.parent
stage = root/'mission-planner-rea-upload'
stage.mkdir(exist_ok=True)
def extended(p):
    return '\\\\?\\' + str(p) if os.name == 'nt' else str(p)
top_files = [p for p in root.iterdir() if p.is_file() and (p.name.endswith('-Trace.md') or p.name in (
    'Reverse-Engineering-Coverage.md','ArduPilot-Organization-Inventory.md','ArduPilot-Source-Map.md',
    'Mission-Planner-Investigation.md','Mission-Planner-Managed-References.md','Mission-Planner-Screen-Map.md',
    'Mission-Planner-UI-Observations.md','research-evidence-verification.json','github-research-preflight.json',
    'mission-planner-installer.msi','mission-planner-payload.cab','mission-planner-portable.zip'))]
roots = ['ardupilot-mavproxy-source','ardupilot-source','mission-planner-1.3.83-source','mission-planner-binary-evidence',
         'mission-planner-isolated','mission-planner-portable','mission-planner-research','mission-planner-runtime',
         'research-tools','sitl-evidence','supportproxy-deps','supportproxy-evidence','supportproxy-source']
files = list(top_files); omitted = []
for name in roots:
    source = root/name
    if not source.exists(): continue
    for directory, dirs, names in os.walk(source, followlinks=False):
        for d in list(dirs):
            candidate = Path(directory)/d
            if d == '.git' or candidate.is_symlink():
                omitted.append({'path':candidate.relative_to(root).as_posix(),'reason':'repository metadata or symlink directory'})
                dirs.remove(d)
        for name in names:
            f = Path(directory)/name
            if name == '.git' or f.is_symlink():
                omitted.append({'path':f.relative_to(root).as_posix(),'reason':'repository metadata or symlink'})
            else: files.append(f)
large = []; errors = []; linked = 0
for f in files:
    rel = f.relative_to(root); target = stage/rel
    try:
        os.makedirs(extended(target.parent),exist_ok=True)
        src, dst = extended(f), extended(target)
        size = os.stat(src).st_size
        if os.path.exists(dst):
            if not os.path.samefile(src,dst): raise OSError('existing staged file does not match source')
        else: os.link(src,dst)
        linked += 1
        if size >= 90_000_000: large.append({'path':rel.as_posix(),'bytes':size})
    except OSError as e:
        if getattr(e,'winerror',None) == 1920:
            omitted.append({'path':rel.as_posix(),'reason':'Windows cannot access this WSL symlink'})
        else: errors.append({'path':rel.as_posix(),'error':str(e)})
    if len(errors) >= 25: break
(stage/'.gitattributes').write_text(''.join(json.dumps(x['path'])+' filter=lfs diff=lfs merge=lfs -text\n' for x in large),encoding='utf-8')
manifest = {'scope':'Mission Planner and ArduPilot reverse engineering research; other drone project documents excluded',
            'source_roots':roots,'candidate_files':len(files),'linked_files':linked,
            'large_files':large,'omitted':omitted,'errors':errors}
(stage/'UPLOAD-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(stage/'README.md').write_text('# Mission Planner REA\n\nResearch, source snapshots, test harnesses and simulator evidence. Start with `Reverse-Engineering-Coverage.md`. See `UPLOAD-MANIFEST.json` for packaging details.\n',encoding='utf-8')
print(json.dumps({'candidate_files':len(files),'large_files':large,'omitted_count':len(omitted),'errors':errors},indent=2))
if errors: raise SystemExit(1)
