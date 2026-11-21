"""Create a plain synthetic JPEG pair and three timed local position records."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import struct
from PIL import Image

SHOT = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
FIXES = [
    (-1, -351260000, 1492400000, 118000),
    (0, -351250000, 1492500000, 120000),
    (1, -351240000, 1492600000, 122000),
]

def x25(data):
    crc = 0xffff
    for byte in data:
        low = byte ^ (crc & 255)
        low ^= (low << 4) & 255
        crc = (crc >> 8) ^ (low << 8) ^ (low << 3) ^ (low >> 4)
    return crc

def create(directory):
    directory.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (32, 24))
    im.putdata([(24 + x * 3, 60 + y * 4, 40 + (x+y) % 12) for y in range(24) for x in range(32)])
    for name in ("nominal", "missing-time"):
        exif = Image.Exif()
        exif[0x010e] = "Synthetic survey swatch"
        if name == "nominal":
            exif[0x8769] = {0x9003: (SHOT + timedelta(hours=5, minutes=30)).strftime("%Y:%m:%d %H:%M:%S")}
        im.save(directory / (name + ".jpg"), quality=88, exif=exif)
    records = bytearray()
    for seq, (seconds, lat, lon, alt) in enumerate(FIXES):
        payload = struct.pack("<IiiiihhhH", 10000 + 1000*seconds, lat, lon, alt, 20000, 0, 0, 0, 0)
        hdr = bytes([len(payload), seq, 1, 1, 33])
        epoch_us = (int(SHOT.timestamp()) + seconds) * 1000000
        records.extend(struct.pack(">Q", epoch_us) + b"\xfe" + hdr + payload + struct.pack("<H", x25(hdr + payload + b"\x68")))
    (directory / "survey.tlog").write_bytes(records)

if __name__ == "__main__":
    create(Path(__file__).resolve().parent / "inputs")
