"""Store omitted Linux symbolic links as Git symlink entries, without dereferencing."""
from pathlib import Path
import json, subprocess
stage = Path(__file__).resolve().parent.parent
root = stage.parent
git_dir = root/'research-upload.git'
manifest_path = stage/'UPLOAD-MANIFEST.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
paths = [x['path'] for x in manifest['omitted'] if 'symlink' in x['reason'] and not x['path'].endswith('/.git')]
linux_root = '/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project'
script = ('import json,os,sys; root=sys.argv[1]; paths=json.loads(sys.argv[2]); '
          'print(json.dumps({p:os.readlink(os.path.join(root,p)) for p in paths}))')
raw = subprocess.check_output(['wsl.exe','-e','python3','-c',script,linux_root,json.dumps(paths)])
targets = json.loads(raw)
git = ['git','--git-dir='+str(git_dir),'--work-tree='+str(stage)]
for path in paths:
    blob = subprocess.check_output(git+['hash-object','-w','--stdin'],input=targets[path].encode('utf-8')).decode().strip()
    subprocess.run(git+['update-index','--add','--cacheinfo','120000',blob,path],check=True)
manifest['restored_symlinks'] = [{'path':p,'target':targets[p]} for p in paths]
manifest['omitted'] = [x for x in manifest['omitted'] if x['path'] not in targets]
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
subprocess.run(git+['add','-f','--','UPLOAD-MANIFEST.json','research-tools/restore-upload-symlinks.py'],cwd=stage,check=True)
print('restored_symlinks',len(paths),'remaining_omissions',len(manifest['omitted']))
