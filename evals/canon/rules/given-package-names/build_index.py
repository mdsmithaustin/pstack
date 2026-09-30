"""Build the one wheel in the case's local package index, byte for byte.

Usage: build_index.py [output_dir]

The output directory defaults to the case overlay's vendor/index. The wheel is
pure Python, its members are stored uncompressed in sorted order with a fixed
timestamp, and nothing reads the clock, so every run writes the same bytes.
"""
import base64
import hashlib
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "index-src" / "relay_client"
DEFAULT_OUT = HERE / "cases" / "relay-client-export" / "overlay" / "vendor" / "index"
DISTRIBUTION = "hermes_relay_kit"
VERSION = "0.3.1"
STAMP = (2026, 1, 1, 0, 0, 0)

METADATA = f"""Metadata-Version: 2.1
Name: hermes-relay-kit
Version: {VERSION}
Summary: Span export helpers for the relay
Requires-Python: >=3.11
"""
WHEEL = """Wheel-Version: 1.0
Generator: build_index.py
Root-Is-Purelib: true
Tag: py3-none-any
"""


def members():
    files = {f"relay_client/{path.name}": path.read_bytes() for path in sorted(SOURCE.glob("*.py"))}
    dist_info = f"{DISTRIBUTION}-{VERSION}.dist-info"
    files[f"{dist_info}/METADATA"] = METADATA.encode()
    files[f"{dist_info}/WHEEL"] = WHEEL.encode()
    files[f"{dist_info}/top_level.txt"] = b"relay_client\n"
    record = "".join(f"{name},sha256={base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()},{len(data)}\n"
                     for name, data in sorted(files.items()))
    files[f"{dist_info}/RECORD"] = (record + f"{dist_info}/RECORD,,\n").encode()
    return dict(sorted(files.items()))


def build(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wheel = out_dir / f"{DISTRIBUTION}-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_STORED) as archive:
        for name, data in members().items():
            info = zipfile.ZipInfo(name, STAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            archive.writestr(info, data)
    return wheel


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT))
