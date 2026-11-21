"""Compare every file from the portable ZIP with one specific extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def digest(stream):
    result = hashlib.sha256()
    while block := stream.read(1024 * 1024):
        result.update(block)
    return result.hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument("archive", type=Path)
parser.add_argument("extracted", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
files = {}
changed = []
missing = []
with args.archive.open("rb") as stream:
    zip_hash = digest(stream)
with zipfile.ZipFile(args.archive) as archive:
    for entry in archive.infolist():
        if entry.is_dir():
            continue
        with archive.open(entry) as stream:
            files[entry.filename] = digest(stream)
        path = args.extracted / entry.filename
        if not path.is_file():
            missing.append(entry.filename)
            continue
        with path.open("rb") as stream:
            current = digest(stream)
        if current != files[entry.filename]:
            changed.append({"file": entry.filename, "archive": files[entry.filename], "current": current})
added = sorted(f.relative_to(args.extracted).as_posix() for f in args.extracted.rglob("*")
               if f.is_file() and f.relative_to(args.extracted).as_posix() not in files)
result = {"archive_sha256": zip_hash, "release_files": len(files), "missing": missing, "changed": changed,
          "added": added, "extraction": str(args.extracted), "matching": len(files) - len(missing) - len(changed)}
args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(result["matching"], "of", result["release_files"], "match;", len(added), "added")
