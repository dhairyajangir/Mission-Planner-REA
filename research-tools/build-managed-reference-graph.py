"""Build a static identity/reference index from the complete REA inventory.

Identity matches are candidates, not CLR binding results. No redirects, probing
paths, dynamically loaded assemblies, or native dependencies are resolved here.
"""
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / 'mission-planner-binary-evidence/managed-references'
PORTABLE = ROOT / 'mission-planner-portable'
OUTPUT = ROOT / 'mission-planner-binary-evidence/managed-reference-graph.sqlite'
SUMMARY = ROOT / 'mission-planner-binary-evidence/managed-reference-graph-summary.json'


def identity(row, ref=False):
    key = row.get('public_key_or_token' if ref else 'public_key') or {}
    return (row['name'].casefold(), row['version'], (row.get('culture') or '').casefold(),
            (key.get('token') or '').lower())


def main():
    manifest = json.loads((EVIDENCE / 'manifest.json').read_text(encoding='utf-8'))
    entries = manifest['results']
    if manifest['requested'] != 260 or len(entries) != 260 or any(x['status'] != 'complete' for x in entries):
        raise RuntimeError('REA inventory is incomplete; no graph written')
    if len({x['path'] for x in entries}) != len(entries):
        raise RuntimeError('duplicate input path')
    records = []
    for entry in entries:
        binary = PORTABLE / entry['path']
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        evidence = json.loads((EVIDENCE / entry['evidence']).read_text(encoding='utf-8'))
        result = evidence['normalized_result']
        if digest != entry['sha256'] or evidence['subject']['digest']['sha256'] != digest:
            raise RuntimeError(f'input digest mismatch: {entry["path"]}')
        if result['coverage']['state'] != 'complete' or result['coverage']['issues'] or not result['assembly']:
            raise RuntimeError(f'incomplete REA metadata: {entry["path"]}')
        records.append((entry, result))

    tmp = OUTPUT.with_suffix('.sqlite.tmp')
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    try:
        db.executescript('''
          CREATE TABLE assemblies (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, sha256 TEXT NOT NULL,
            name TEXT NOT NULL, version TEXT NOT NULL, culture TEXT NOT NULL, public_key_token TEXT NOT NULL,
            evidence TEXT NOT NULL);
          CREATE TABLE assembly_references (id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES assemblies(id),
            metadata_token TEXT, name TEXT NOT NULL, version TEXT NOT NULL, culture TEXT NOT NULL,
            public_key_token TEXT NOT NULL, exact_candidate_count INTEGER NOT NULL,
            same_name_candidate_count INTEGER NOT NULL);
          CREATE TABLE exact_candidates (reference_id INTEGER NOT NULL REFERENCES assembly_references(id),
            assembly_id INTEGER NOT NULL REFERENCES assemblies(id), PRIMARY KEY(reference_id, assembly_id));
          CREATE INDEX references_source ON assembly_references(source_id);
          CREATE INDEX assembly_names ON assemblies(name);
        ''')
        exact, names = {}, {}
        for i, (entry, result) in enumerate(records, 1):
            assembly = result['assembly']
            key = identity(assembly)
            exact.setdefault(key, []).append(i)
            names.setdefault(key[0], []).append(i)
            db.execute('INSERT INTO assemblies VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (i, entry['path'], entry['sha256'], assembly['name'], key[1], key[2], key[3], entry['evidence']))
        for i, (_, result) in enumerate(records, 1):
            for ref in result['references']:
                key = identity(ref, True)
                candidates = exact.get(key, [])
                cursor = db.execute('INSERT INTO assembly_references(source_id,metadata_token,name,version,culture,public_key_token,exact_candidate_count,same_name_candidate_count) VALUES (?,?,?,?,?,?,?,?)',
                                    (i, ref.get('token'), ref['name'], key[1], key[2], key[3], len(candidates), len(names.get(key[0], []))))
                db.executemany('INSERT INTO exact_candidates VALUES (?, ?)', ((cursor.lastrowid, c) for c in candidates))
        db.commit()
        counts = {'assemblies': db.execute('SELECT COUNT(*) FROM assemblies').fetchone()[0],
                  'references': db.execute('SELECT COUNT(*) FROM assembly_references').fetchone()[0],
                  'references_no_exact_candidate': db.execute('SELECT COUNT(*) FROM assembly_references WHERE exact_candidate_count=0').fetchone()[0],
                  'references_one_exact_candidate': db.execute('SELECT COUNT(*) FROM assembly_references WHERE exact_candidate_count=1').fetchone()[0],
                  'references_multiple_exact_candidates': db.execute('SELECT COUNT(*) FROM assembly_references WHERE exact_candidate_count>1').fetchone()[0],
                  'references_no_exact_but_same_name': db.execute('SELECT COUNT(*) FROM assembly_references WHERE exact_candidate_count=0 AND same_name_candidate_count>0').fetchone()[0],
                  'candidate_edges': db.execute('SELECT COUNT(*) FROM exact_candidates').fetchone()[0]}
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('SQLite integrity check failed')
    finally:
        db.close()
    tmp.replace(OUTPUT)
    summary = {'counts': counts, 'sqlite_sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
               'manifest_sha256': hashlib.sha256((EVIDENCE / 'manifest.json').read_bytes()).hexdigest(),
               'limitations': ['Matches use declared name, version, culture and public-key token only.',
                               'No CLR binding, redirects, probing paths, native or dynamically loaded dependencies were resolved.',
                               'A missing exact candidate can be a framework assembly, an external dependency, or another version.']}
    SUMMARY.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
