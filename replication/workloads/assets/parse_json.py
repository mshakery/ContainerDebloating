import hashlib
import json
import sys

PAYLOAD = json.dumps({
    "name": "greenlab",
    "vals": list(range(128)),
    "nested": {"k": "v" * 64, "n": [i * i for i in range(64)]},
})

def main() -> int:
    n = int(sys.argv[1])
    h = hashlib.sha256()
    obj = json.loads(PAYLOAD)
    h.update(json.dumps(obj, sort_keys=True).encode("utf-8"))
    print(f"COLD {h.copy().hexdigest()}", flush=True)
    for _ in range(1, n):
        obj = json.loads(PAYLOAD)
        h.update(json.dumps(obj, sort_keys=True).encode("utf-8"))
    print(f"STEADY {h.hexdigest()}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
