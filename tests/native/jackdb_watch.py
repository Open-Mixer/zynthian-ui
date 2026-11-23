"""pytest plugin (repro only): name the test after which libjack's metadata environment first exists, and who holds it."""
import os
import subprocess
import time

DB = f"/dev/shm/jack_db-{os.getuid()}"
_seen = {"done": False}


def _report(when, nodeid):
    files = []
    for f in sorted(os.listdir(DB)) if os.path.isdir(DB) else []:
        st = os.stat(os.path.join(DB, f))
        files.append(f"{f} {st.st_size}B mtime={time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}")
    maps = [line.split()[-1] for line in open("/proc/self/maps") if "jack_db" in line]
    holders = subprocess.run(["sh", "-c", f"lsof +D {DB} 2>/dev/null; ps -eo pid,ppid,comm,args | grep -i jack | grep -v grep"],
                             capture_output=True, text=True).stdout
    print(f"\n[jackdb-watch] {DB} exists {when} {nodeid} at {time.strftime('%H:%M:%S')}; files {files}; "
          f"mapped here {sorted(set(maps))}; threads here {len(os.listdir('/proc/self/task'))}\n{holders}", flush=True)


def pytest_runtest_logfinish(nodeid, location):
    if not _seen["done"] and os.path.isdir(DB):
        _seen["done"] = True
        _report("after", nodeid)


def pytest_sessionstart(session):
    if os.path.isdir(DB):
        _seen["done"] = True
        _report("at session start", "")
