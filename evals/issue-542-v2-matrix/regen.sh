#!/bin/sh
# Rebuild every extract from the saved run directories. Usage: regen.sh RUNS_DIR
set -e
cd "$(dirname "$0")"
R=$1
for r in how why arena architect swarm interrogate reflect poteto-mode trail-reviewer; do python3 reduce.py "$R/$r-1" --out "extracts/$r-attempt1.json" >/dev/null; done
python3 reduce.py "$R/how-v1-1" --row how-v1-flag-on --out extracts/how-v1-flag-on-attempt1.json >/dev/null
python3 reduce.py "$R/how-v1-2" --out extracts/how-v1-attempt1.json >/dev/null
python3 reduce.py "$R/how-v1-3" --out extracts/how-v1-attempt2.json >/dev/null
python3 reduce.py "$R/reflect-2" --out extracts/reflect-attempt2.json >/dev/null
python3 reduce.py "$R/poteto-mode-2" --out extracts/poteto-mode-attempt2.json >/dev/null
