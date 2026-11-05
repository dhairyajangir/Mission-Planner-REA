"""Compare ZIP file contents to an authoritative GitHub Git tree's blob IDs."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent.parent
archive = Path(r'C:\Users\think\OneDrive\Desktop\Projects\drone\ardupilot-master.zip')
tree = json.loads((root / 'research-tools/archive-candidate-tree.json').read_text(encoding='utf-8'))
if tree.get('truncated') or not isinstance(tree.get('tree'), list):
    raise ValueError('GitHub tree is incomplete')
blobs = {x['path']: x['sha'] for x in tree['tree'] if x['type'] == 'blob'}
gitlinks = [{'path': x['path'], 'sha': x['sha']} for x in tree['tree'] if x['type'] == 'commit']
seen = set()
extra = []
mismatches = []
with zipfile.ZipFile(archive) as z:
    comment = z.comment.decode('ascii')
    for entry in z.infolist():
        if entry.is_dir():
            continue
        prefix = 'ardupilot-master/'
        if not entry.filename.startswith(prefix):
            raise ValueError(f'unexpected archive path {entry.filename!r}')
        name = entry.filename[len(prefix):]
        if name in seen:
            raise ValueError(f'duplicate ZIP path {name!r}')
        seen.add(name)
        if name not in blobs:
            extra.append(name)
            continue
        h = hashlib.sha1(f'blob {entry.file_size}\0'.encode('ascii'))
        with z.open(entry) as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        digest = h.hexdigest()
        if digest != blobs[name]:
            mismatches.append({'path': name, 'expected_git_blob': blobs[name], 'actual_git_blob': digest})
missing = sorted(set(blobs) - seen)
result = {'candidate_commit_from_zip_comment': comment, 'git_tree_response_sha': tree.get('sha'),
          'tree_truncated': tree['truncated'], 'zip_files': len(seen), 'upstream_blob_count': len(blobs),
          'matched_blobs': len(seen) - len(extra) - len(mismatches), 'extra_zip_paths': extra,
          'missing_upstream_paths': missing, 'mismatches': mismatches, 'submodule_gitlinks': gitlinks,
          'limitations': ['Git blob comparisons cover regular archive entries, not initialized submodule contents.',
                          'The archive comment and upstream tree corroborate the revision; this does not verify a local build or runtime binary.']}
out = root / 'ardupilot-source/archive-provenance.json'
out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: result[k] for k in ('candidate_commit_from_zip_comment', 'git_tree_response_sha',
                                       'zip_files', 'upstream_blob_count', 'matched_blobs')}, indent=2))
print('extra', len(extra), 'missing', len(missing), 'mismatches', len(mismatches), 'gitlinks', len(gitlinks))
if comment != tree['sha'] or extra or missing or mismatches:
    raise SystemExit(1)
