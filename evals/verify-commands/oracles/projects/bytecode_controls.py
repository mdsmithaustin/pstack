import hashlib
import json
import os
import py_compile
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()
sys.pycache_prefix = None
state = sys.argv[2]
controls = {
    "baseline": ("baseline", "baseline"),
    "mutated": ("baseline", "mutation"),
    "restored": ("mutation", "baseline"),
}
if state not in controls:
    raise SystemExit(f"unknown state: {state}")
cached_value, source_value = controls[state]
(root / "tools").mkdir(parents=True, exist_ok=True)
source = root / "tools" / "subject.py"
source.write_text(f"def value():\n    return '{cached_value}'\n")
os.utime(source, (1700000000, 1700000000))
cache = Path(py_compile.compile(str(source), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP))
before = source.stat()
source.write_text(f"def value():\n    return '{source_value}'\n")
os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
after = source.stat()
if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
    raise SystemExit("source replacement changed cache validation metadata")
(root / "tools" / "observe.py").write_text(
    "import subject\n"
    "observed_behavior = subject.value()\n"
    "observed_cache = subject.__cached__\n"
    "print(observed_behavior, flush=True)\n"
)
(root / "expected.txt").write_text(source_value + "\n")
print(json.dumps({
    "state": state,
    "source_size": after.st_size,
    "source_mtime_ns": after.st_mtime_ns,
    "seeded_cache": str(cache.relative_to(root)),
    "cache_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
    "cache_header_hex": cache.read_bytes()[:16].hex(),
    "cached_value": cached_value,
    "intended_value": source_value,
}, sort_keys=True))
