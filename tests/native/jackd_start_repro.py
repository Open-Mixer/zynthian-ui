"""Start and stop private dummy jackd servers the way the native fixture does, and report every failure."""
import os
import sys
import time
import uuid

sys.path.insert(0, os.getcwd())
from tests.jacktest import JackTestServer  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
fails = 0
for i in range(n):
    s = JackTestServer(f"zyntest_{os.getpid()}_{uuid.uuid4().hex[:6]}", die_with_parent=True)
    t = time.monotonic()
    try:
        s.start()
        print(f"start {i} ok {time.monotonic() - t:.2f}s", flush=True)
    except RuntimeError as e:
        fails += 1
        print(f"start {i} FAILED: {e}", flush=True)
    s.stop()
print(f"{fails}/{n} failed")
sys.exit(1 if fails else 0)
