"""Compare pinned upstream source anchors with the two tested SITL binaries."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
old_root = root / 'sitl-evidence/legacy-fence-source'
new_root = root / 'ardupilot-source/ardupilot-master'
rows = [
    ('GCS_Fence.cpp', 'libraries/GCS_MAVLink/GCS_Fence.cpp', 'b3bfb78a37194fdfbd5d78dd355785532701fd38', 'f1e305ff72ecd71b1e9271db56a3ff19bda556b0'),
    ('GCS_Common.cpp', 'libraries/GCS_MAVLink/GCS_Common.cpp', 'da5d47e30e6d1b2501a8e4302cf4c7bf1f05d22d', '310c4debab0f2df72265592eb8955518e86011ed'),
    ('AC_Fence_config.h', 'libraries/AC_Fence/AC_Fence_config.h', 'e3b83081f720add3d71a6f2094f1038ce1462e61', '23707a539351424d8a591d849172eac9af7cff14'),
    ('AC_PolyFence_loader.cpp', 'libraries/AC_Fence/AC_PolyFence_loader.cpp', 'b77eabcae746f29f14453160b8678789c190bcc8', '9843fafafc781c040c8362ae2e4caf9d08d5fbc5'),
    ('AC_PolyFence_loader.h', 'libraries/AC_Fence/AC_PolyFence_loader.h', '1a4b3ce6decc8d13179f417a63fa5441ca960a8a', 'e09a38099c64ffcbdf8095bff37bc95073ca85f7')]
def blob(path):
    data = path.read_bytes()
    return hashlib.sha1(('blob ' + str(len(data)) + '\0').encode() + data).hexdigest()
tree = json.loads((root / 'research-tools/archive-candidate-tree.json').read_text())
assert tree['sha'] == '72b238201f5ea3b556e3809b2ec704fcf701474a'
entries = {item['path']: item['sha'] for item in tree['tree']}
files = []
for local, repo, old_sha, new_sha in rows:
    assert blob(old_root / local) == old_sha and blob(new_root / repo) == new_sha and entries[repo] == new_sha
    files.append({'repository_path': repo, 'old_file': str((old_root / local).relative_to(root)).replace('\\','/'),
                  'old_git_blob_sha1': old_sha, 'new_git_blob_sha1': new_sha})
old_fence = (old_root / 'GCS_Fence.cpp').read_text(encoding='utf8')
old_common = (old_root / 'GCS_Common.cpp').read_text(encoding='utf8')
old_config = (old_root / 'AC_Fence_config.h').read_text(encoding='utf8')
new_fence = (new_root / rows[0][1]).read_text(encoding='utf8')
new_common = (new_root / rows[1][1]).read_text(encoding='utf8')
new_config = (new_root / rows[2][1]).read_text(encoding='utf8')
assert '#if AC_POLYFENCE_FENCE_POINT_PROTOCOL_SUPPORT' in old_fence and 'MAVLINK_MSG_ID_FENCE_FETCH_POINT' in old_fence
assert 'handle_fence_message(msg)' in old_common and 'send_received_message_deprecation_warning("FENCE_FETCH_POINT")' in old_common
assert '#define AC_POLYFENCE_FENCE_POINT_PROTOCOL_SUPPORT 0' in old_config and 'ArduPilot 4.8 removes the code entirely' in old_config
assert 'handle_fence_message' not in new_fence and 'MAVLINK_MSG_ID_FENCE_FETCH_POINT' not in new_common
assert 'AC_POLYFENCE_FENCE_POINT_PROTOCOL_SUPPORT' not in new_config
binary = {}
for name, path in [('prebuilt_4_7_2', root / 'sitl-evidence/arducopter'), ('source_built_4_8_dev', root / 'sitl-evidence/archive-built/arducopter')]:
    raw = path.read_bytes()
    binary[name] = {'sha256': hashlib.sha256(raw).hexdigest(),
                    'legacy_dispatch_string_count': raw.count(b'Unhandled common fence message'),
                    'legacy_fetch_string_count': raw.count(b'FENCE_FETCH_POINT')}
assert binary['prebuilt_4_7_2']['legacy_dispatch_string_count'] > 0 and binary['prebuilt_4_7_2']['legacy_fetch_string_count'] > 0
assert binary['source_built_4_8_dev']['legacy_dispatch_string_count'] == binary['source_built_4_8_dev']['legacy_fetch_string_count'] == 0
summary = {'scope': 'Selected source files and static binary strings; build-to-source equivalence not proven',
           'old_source_commit': 'fb773567896014da007bca58358704d4a0d8516f', 'old_binary_reported_revision_prefix': 'fb773567',
           'new_source_commit': tree['sha'], 'old_file_source': 'GitHub API at pinned commit', 'files': files,
           'binaries': binary}
out = old_root / 'comparison.json'
out.write_text(json.dumps(summary, indent=2) + '\n')
print('Verified', len(files), 'old/new Git blobs and selected binary string anchors')
