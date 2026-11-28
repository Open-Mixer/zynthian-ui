#!/usr/bin/env python3
"""served_pair.py: the newest version a set of packages is served at TOGETHER in one cell of the OpenMixer channel.

  python3 tools/served_pair.py [--channel URL]... [--cell SUITE/ARCH] PACKAGE...

Reads the channel's deb/cells.tsv (`# package<TAB>version<TAB>set<TAB>cells`, the file the channel's served.sh
reads) and prints the newest version every PACKAGE carries in the cell; an `all` row counts for every architecture of
its suite. A release that has reached only some cells (published for one architecture, not yet for another) is then
not this cell's version, and the CI installs the pair the cell does serve instead of reading the gap as its own red.
With --channel given more than once (the channel levels a job reads: the real channel, staging, a devel wave and its
base waves, every tree apt has a source for), the trees are read together: a package served in any of them is served
to the cell, so a pair split across levels counts where both halves are served at one version. The first --channel
must answer; a later tree that answers 404 (a wave that never published) is skipped, saying so.
Exit 1 when no version is served together in the cell, 2 when a file is not a cells.tsv.
"""
import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request


def _order(c):
    if c == "~":
        return -1
    if c.isalpha():
        return ord(c)
    return ord(c) + 256


def vercmp(a, b):
    """Debian's version order on an upstream version (~ sorts first)."""
    while a or b:
        na = re.match(r"\D*", a).group(0)
        nb = re.match(r"\D*", b).group(0)
        for x, y in zip(list(na) + [""] * len(nb), list(nb) + [""] * len(na)):
            ox = _order(x) if x else 0
            oy = _order(y) if y else 0
            if ox != oy:
                return -1 if ox < oy else 1
        a, b = a[len(na):], b[len(nb):]
        da = re.match(r"\d*", a).group(0)
        db = re.match(r"\d*", b).group(0)
        if int(da or 0) != int(db or 0):
            return -1 if int(da or 0) < int(db or 0) else 1
        a, b = a[len(da):], b[len(db):]
    return 0


HEADER = "# package\t"


def merge_cells(texts):
    """One cells.tsv of every level's rows, the first level's header kept: a tree whose file is not a cells.tsv is an
    error naming its position, never read as a tree serving nothing."""
    rows = []
    for i, text in enumerate(texts):
        lines = text.splitlines()
        if not lines or not lines[0].startswith(HEADER):
            raise ValueError(f"channel {i + 1} is not a cells.tsv (no '# package' header)")
        rows.extend(lines[0:1] if i == 0 else [])
        rows.extend(lines[1:])
    return "\n".join(rows) + "\n"


def served_pair(cells_tsv, cell, packages):
    lines = cells_tsv.splitlines()
    if not lines or not lines[0].startswith(HEADER):
        raise ValueError("not a cells.tsv (no '# package' header)")
    suite = cell.split("/")[0]
    carried = {}
    for line in lines[1:]:
        if not line or line.startswith("#"):
            continue
        name, version, _set, cells = line.split("\t")[:4]
        if cell in cells.split() or f"{suite}/all" in cells.split():
            carried.setdefault(name, set()).add(version)
    together = set.intersection(*(carried.get(p, set()) for p in packages))
    if not together:
        raise LookupError(f"no version of {' '.join(packages)} is served together in {cell}")
    best = None
    for v in together:
        if best is None or vercmp(v, best) > 0:
            best = v
    return best


def main():
    ap = argparse.ArgumentParser(prog="served_pair.py")
    ap.add_argument("--channel", action="append", default=[])
    ap.add_argument("--cell", default="")
    ap.add_argument("packages", nargs="+")
    a = ap.parse_args()
    cell = a.cell
    if not cell:
        suite = re.search(r"^VERSION_CODENAME=(\S+)", open("/etc/os-release").read(), re.M).group(1)
        arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, check=True).stdout.strip()
        cell = f"{suite}/{arch}"
    channels = a.channel or ["https://www.openmixer.org"]
    try:
        texts = []
        for i, channel in enumerate(channels):
            url = f"{channel.rstrip('/')}/deb/cells.tsv"
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    texts.append(r.read().decode())
            except urllib.error.HTTPError as e:
                if i == 0 or e.code != 404:
                    raise
                print(f"served_pair: {url} answered 404 (never published): skipped", file=sys.stderr)
        print(served_pair(merge_cells(texts), cell, a.packages))
    except ValueError as e:
        print(f"served_pair: {e}", file=sys.stderr)
        return 2
    except LookupError as e:
        print(f"served_pair: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
