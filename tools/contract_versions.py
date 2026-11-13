#!/usr/bin/env python3
"""contract_versions.py: the contract versions the series is built and tested against, and the check of what is
installed.

  python3 tools/contract_versions.py [--file contract-versions]

contract-versions declares, one line each, `<name> >= <floor> < <ceiling>`, optionally followed by `: <package>...`,
the binary packages that carry it (default: the name itself). The check reads each package's installed version
(dpkg-query) and names every one below its floor or at its ceiling, and every declared package not installed: exit 1
with the lines, 0 when the installed set is inside the declaration. Outward requires the latest: when the channel
serves a newer contract, the floor line moves.
"""
import argparse
import re
import subprocess
import sys

from tools.served_pair import vercmp

LINE = re.compile(r"^(\S+)\s*>=\s*(\S+)\s*<\s*(\S+)(?:\s*:\s*(.+))?$")


def _lines(text):
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            m = LINE.match(line)
            if not m:
                raise ValueError(f"contract-versions line {n} is not '<name> >= <floor> < <ceiling>': {line}")
            yield m


def parse(text):
    """{name: (floor, ceiling)}"""
    return {m.group(1): (m.group(2), m.group(3)) for m in _lines(text)}


def packages(text):
    """{name: [binary package, ...]}"""
    return {m.group(1): (m.group(4).split() if m.group(4) else [m.group(1)]) for m in _lines(text)}


def check(ranges, installed):
    """the lines naming what is outside its range; installed is {name: version}"""
    bad = []
    for name, (floor, ceiling) in ranges.items():
        v = installed.get(name)
        if v is None:
            bad.append(f"{name} is not installed")
        elif vercmp(v, floor) < 0:
            bad.append(f"{name} {v} is below the declared floor {floor}")
        elif vercmp(v, ceiling) >= 0:
            bad.append(f"{name} {v} is at or above the declared ceiling {ceiling}")
    return bad


def main():
    ap = argparse.ArgumentParser(prog="contract_versions.py")
    ap.add_argument("--file", default="contract-versions")
    a = ap.parse_args()
    text = open(a.file).read()
    ranges, bad = parse(text), []
    for name, pkgs in packages(text).items():
        for p in pkgs:
            r = subprocess.run(["dpkg-query", "-W", "-f", "${Version}", p], capture_output=True, text=True)
            got = {name: r.stdout.strip()} if r.returncode == 0 and r.stdout.strip() else {}
            bad += [b.replace(name, p, 1) for b in check({name: ranges[name]}, got)]
            if got:
                print(f"{p} {got[name]} (declared {name} >= {ranges[name][0]} < {ranges[name][1]})")
    for b in bad:
        print(f"contract-versions: {b}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
