import hashlib
import os
import sys

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import torch

torch.manual_seed(0)
torch.use_deterministic_algorithms(True, warn_only=True)
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

def build_model() -> torch.nn.Module:
    g = torch.Generator().manual_seed(0)
    l1 = torch.nn.Linear(64, 32)
    l2 = torch.nn.Linear(32, 10)
    with torch.no_grad():
        torch.nn.init.xavier_uniform_(l1.weight, generator=g)
        torch.nn.init.zeros_(l1.bias)
        torch.nn.init.xavier_uniform_(l2.weight, generator=g)
        torch.nn.init.zeros_(l2.bias)
    m = torch.nn.Sequential(l1, torch.nn.ReLU(), l2, torch.nn.Softmax(dim=-1))
    m.eval()
    return m

def main() -> int:
    n = int(sys.argv[1])
    model = build_model()
    x = torch.full((8, 64), 0.1, dtype=torch.float32)
    h = hashlib.sha256()
    with torch.no_grad():
        y = model(x).numpy()
        h.update(y.tobytes())
        print(f"COLD {hashlib.sha256(y.tobytes()).hexdigest()}", flush=True)
        for _ in range(1, n):
            y = model(x).numpy()
            h.update(y.tobytes())
    print(f"STEADY {h.hexdigest()}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
