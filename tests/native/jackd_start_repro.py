"""Start and stop private dummy jackd servers the way the native fixture does, and report every failure.

With --fresh-db, libjack's metadata environment (/dev/shm/jack_db) is removed before every start, so each
start is a first start on a fresh machine, as on a new CI runner."""
import os
import shutil
import sys
import time
import uuid

sys.path.insert(0, os.getcwd())
from tests.jacktest import JackTestServer  # noqa: E402

fresh = "--fresh-db" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
n = int(args[0]) if args else 20
fails = 0
for i in range(n):
    if fresh:
        shutil.rmtree("/dev/shm/jack_db", ignore_errors=True)
    s = JackTestServer(f"zyntest_{os.getpid()}_{uuid.uuid4().hex[:6]}")
    t = time.monotonic()
    try:
        s.start(timeout=10)
        print(f"start {i} ok {time.monotonic() - t:.2f}s", flush=True)
    except RuntimeError as e:
        fails += 1
        print(f"start {i} FAILED: {str(e).splitlines()[0]}", flush=True)
        print("\n".join(line for line in str(e).splitlines() if "BDB" in line or "DB env" in line), flush=True)
    s.stop()
print(f"{fails}/{n} failed{' (fresh jack_db every start)' if fresh else ''}")
sys.exit(1 if fails else 0)
