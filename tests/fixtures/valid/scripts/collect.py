import json
import sys

json.load(sys.stdin)
print(json.dumps({"items": [{"id": 1}, {"id": 2}]}))
