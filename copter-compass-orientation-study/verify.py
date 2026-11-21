"""Check the sampled fit and the missing vertical information independently."""
import json
import math
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
TRUTH = (-120, 80, -150)


def verify():
    record = json.loads((HERE / "fit-results.json").read_text())
    fits = record["fits"]
    if record["method"] != {"token": "06000168", "module_version_id": "b0e70e19-ad56-4dc7-bb0b-8e33a4ca21c0"}:
        raise ValueError("Unexpected method")
    if any(fits[name]["count"] != 122 for name in ("full_sphere", "level_ring", "ring_plus_poles")):
        raise ValueError("Unexpected fixture sizes")
    for name in ("full_sphere", "ring_plus_poles"):
        result = fits[name]["offset_xyz_radius"]
        if math.dist(result, (*TRUTH, 500)) >= 0.00001:
            raise ValueError("3D control did not recover the simulated offset and radius")
    x, y, z, radius = fits["level_ring"]["offset_xyz_radius"]
    residuals = []
    for i in range(122):
        angle = 2 * math.pi * i / 122
        sample = struct.unpack("<fff", struct.pack("<fff", 120 + 500 * math.cos(angle),
                                                   -80 + 500 * math.sin(angle), 150))
        residuals.append(abs(math.hypot(sample[0] + x, sample[1] + y, sample[2] + z) - radius))
    polar_fields = [math.hypot(120 + x, -80 + y, 150 + z + pole) for pole in (-500, 500)]
    if (max(residuals) >= 0.0001 or abs(z + 150) <= 140
            or not (356.22 < polar_fields[0] < 356.24 and 643.76 < polar_fields[1] < 643.79)):
        raise ValueError("Planar fit no longer matches the measured orientation error")
    return {"vertical_offset_error": abs(z + 150), "max_training_residual": max(residuals),
            "held_out_polar_magnitudes": polar_fields}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
