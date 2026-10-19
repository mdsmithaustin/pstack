import json
import sys

json.load(sys.stdin)
print(json.dumps({"error": "not_implemented"}))
