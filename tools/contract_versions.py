#!/usr/bin/env python3
"""contract_versions.py: the contract packages the series is built and tested against, by name, and the check of
what is installed.

  python3 tools/contract_versions.py [--file contract-versions] [--packages]

contract-versions names, one line each, `<name>`, optionally followed by `: <package>...`, the binary packages that
carry it (default: the name itself). Names only (owner rule, 2026-11-24: no hand-kept floors): the series uses the
package the channel publishes, so a line carrying a version relation (>=, <=, =, <, >) is refused, and a floor is
removed, never bumped. --packages prints every binary package, one per line, for the install step to install by
name. The check reads each package's installed version (dpkg-query), prints it, and names every declared package not
installed: exit 1 with the lines, 0 when all are installed.
"""
import argparse
import re
import subprocess
import sys

LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9.+-]*)(?:\s*:\s*(.+))?$")
RELATION = re.compile(r"[<>=]")


def _lines(text):
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            if RELATION.search(line):
                raise ValueError(f"contract-versions line {n} carries a version relation, and names only are declared "
                                 f"(the channel's package, never a floor): {line}")
            m = LINE.match(line)
            if not m:
                raise ValueError(f"contract-versions line {n} is not '<name> [: <package>...]': {line}")
            yield m


def parse(text):
    """[name, ...] in the file's order"""
    return [m.group(1) for m in _lines(text)]


def packages(text):
    """{name: [binary package, ...]}"""
    return {m.group(1): (m.group(2).split() if m.group(2) else [m.group(1)]) for m in _lines(text)}


def check(names, installed):
    """the lines naming each declared package that is not installed; installed is {name: version}"""
    return [f"{name} is not installed" for name in names if not installed.get(name)]


def main():
    ap = argparse.ArgumentParser(prog="contract_versions.py")
    ap.add_argument("--file", default="contract-versions")
    ap.add_argument("--packages", action="store_true", help="print the binary packages to install, one per line")
    a = ap.parse_args()
    with open(a.file) as f:
        text = f.read()
    pkgs = [p for ps in packages(text).values() for p in ps]
    if a.packages:
        print("\n".join(pkgs))
        return 0
    installed = {}
    for p in pkgs:
        r = subprocess.run(["dpkg-query", "-W", "-f", "${Version}", p], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            installed[p] = r.stdout.strip()
            print(f"{p} {installed[p]}")
    bad = check(pkgs, installed)
    for b in bad:
        print(f"contract-versions: {b}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
