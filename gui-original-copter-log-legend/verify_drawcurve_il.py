"""Verify the pinned ZedGraph DrawCurve IL bytes from the portable ZIP and the REA method index."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DLL_SHA256 = "5b1c254d4e1dbb767870272231664a0ea57f33e401b677abb2bcb2129a86efd5"
IL_SHA256 = "fcd0965750afae9e9fc16c8661e68b883bf8d2e4367a73c9929e9ec829c548fe"
TOKEN = "0x0600033d"
RVA = 0x11FC0  # Mono.Cecil disassembly of this exact release DLL; see the adjacent listing.


def verify(root=ROOT):
    """Return verified method identity and hashes, or raise on any mismatch. Reads only."""
    root = Path(root)
    with zipfile.ZipFile(root / "mission-planner-portable.zip") as archive:
        dll = archive.read("ZedGraph.dll")
    if hashlib.sha256(dll).hexdigest() != DLL_SHA256:
        raise ValueError("Unexpected ZedGraph.dll in the release archive")
    index = root / "mission-planner-binary-evidence/rea-remaining-index.sqlite"
    db = sqlite3.connect(index.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = db.execute("SELECT declaring_type, name, body_status, il_sha256 FROM methods "
                         "WHERE assembly = ? AND token = ?", ("ZedGraph.dll", TOKEN)).fetchone()
    finally:
        db.close()
    if row != ("ZedGraph.Line", "DrawCurve", "present", IL_SHA256):
        raise ValueError("Unexpected REA method identity or IL digest")

    pe = struct.unpack_from("<I", dll, 0x3C)[0]
    sections = struct.unpack_from("<H", dll, pe + 6)[0]
    optional_size = struct.unpack_from("<H", dll, pe + 20)[0]
    for i in range(sections):
        section = pe + 24 + optional_size + 40 * i
        address, size, raw = struct.unpack_from("<III", dll, section + 12)
        if address <= RVA < address + size:
            method = raw + RVA - address
            break
    else:
        raise ValueError("Pinned method RVA falls outside the PE sections")
    flags, size = struct.unpack_from("<H2xI", dll, method)
    start = method + 4 * (flags >> 12)
    if flags & 3 != 3 or size != 1443:
        raise ValueError("Unexpected managed method header or code size")
    digest = hashlib.sha256(dll[start:start + size]).hexdigest()
    if digest != IL_SHA256:
        raise ValueError("Release IL stream differs from the pinned method")
    return {"assembly": "ZedGraph.dll", "method": row[0] + "." + row[1], "token": TOKEN,
            "rva": hex(RVA), "code_bytes": size, "il_sha256": digest, "dll_sha256": DLL_SHA256}


if __name__ == "__main__":
    print(json.dumps(verify()))
