"""pytest plugin (repro only): report every change of libjack's metadata environment, test by test, and who holds it."""
import os
import subprocess
import time

DB = f"/dev/shm/jack_db-{os.getuid()}"
_last = {"state": None}


def _state():
    if not os.path.isdir(DB):
        return None
    files = []
    for f in sorted(os.listdir(DB)):
        try:
            st = os.stat(os.path.join(DB, f))
            files.append(f"{f}:{st.st_size}B@{time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}")
        except OSError:
            files.append(f"{f}:gone")
    return tuple(files)


def _report(when, nodeid, state):
    me = os.getpid()
    out = subprocess.run(["sh", "-c", f"grep -l jack_db /proc/[0-9]*/maps 2>/dev/null; "
                                      f"ps -o pid,ppid,stat,etime,args --ppid {me} 2>/dev/null"],
                         capture_output=True, text=True).stdout
    print(f"\n[jackdb-watch] {when} {nodeid} at {time.strftime('%H:%M:%S')}: {DB} "
          f"{'absent' if state is None else list(state)}; threads here {len(os.listdir('/proc/self/task'))}\n{out}",
          flush=True)


def pytest_runtest_logfinish(nodeid, location):
    state = _state()
    if state != _last["state"]:
        _last["state"] = state
        _report("changed after", nodeid, state)


def pytest_runtest_setup(item):
    if "native" in str(item.fspath) and not _last.get("native"):
        _last["native"] = True
        _report("before the first native test", item.nodeid, _state())


def pytest_sessionstart(session):
    _last["state"] = _state()
    _report("at session start", "", _last["state"])
