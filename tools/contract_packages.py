#!/usr/bin/env python3
"""contract_packages.py: the contract packages the series is built and tested against, and the check of what is
installed.

  python3 -m tools.contract_packages [--file contract-packages]

contract-packages declares, one line each, `<binary package> [<path>...]`: the package must be installed, and each
path it names (a domain directory, a document, a module the code reads) must exist and belong to that package. No
version is declared: a floor typed here is a hand-kept floor, and the owner's rule is that the next level uses the
published package, nothing else (a floor of 3.14.0 on omx-contract-data could never pass once packages were
numbered 0.M.m). A line carrying a version relation (>=, <=, <<, >>, =, <, >) or a version number is refused. The
check prints the version each package has, read from dpkg: the record of what the run was tested against, derived,
never typed. Exit 1 naming every package not installed and every path missing or owned by another package, 0
otherwise.
"""
import argparse
import os
import re
import subprocess
import sys

NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
RELATION = re.compile(r"(>=|<=|<<|>>|=|<|>)")
VERSION = re.compile(r"^\(?\d+(\.\d+)+")


def parse(text):
    """{package: [path, ...]} in declaration order"""
    out = {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if RELATION.search(line):
            raise ValueError(f"contract-packages line {n} carries a version relation, and no floor is kept by hand: "
                             f"{line}")
        words = line.split()
        if not NAME.match(words[0]):
            raise ValueError(f"contract-packages line {n} does not start with a package name: {line}")
        for w in words[1:]:
            if VERSION.match(w):
                raise ValueError(f"contract-packages line {n} carries a version, and no floor is kept by hand: {line}")
            if not w.startswith("/"):
                raise ValueError(f"contract-packages line {n}: '{w}' is not an absolute path: {line}")
        if words[0] in out:
            raise ValueError(f"contract-packages line {n} declares {words[0]} a second time")
        out[words[0]] = words[1:]
    return out


def check(declared, installed, owned, exists):
    """the lines naming what is not installed or not laid down. installed is {package: version}, owned is
    {package: set of paths dpkg lists for it}, exists(path) answers whether the path is on disk."""
    bad = []
    for pkg, paths in declared.items():
        if pkg not in installed:
            bad.append(f"{pkg} is not installed")
            continue
        for p in paths:
            if not exists(p):
                bad.append(f"{pkg} {installed[pkg]}: {p} is missing")
            elif p not in owned.get(pkg, set()):
                bad.append(f"{pkg} {installed[pkg]}: {p} is not laid down by {pkg}")
    return bad


def _dpkg(pkg):
    r = subprocess.run(["dpkg-query", "-W", "-f", "${db:Status-Status} ${Version}", pkg], capture_output=True,
                       text=True)
    status, _, version = r.stdout.strip().partition(" ")
    if r.returncode != 0 or status != "installed" or not version:
        return None, set()
    files = subprocess.run(["dpkg-query", "-L", pkg], capture_output=True, text=True).stdout.split("\n")
    return version, {f.rstrip("/") for f in files if f}


def main():
    ap = argparse.ArgumentParser(prog="contract_packages.py")
    ap.add_argument("--file", default="contract-packages")
    a = ap.parse_args()
    with open(a.file) as f:
        declared = parse(f.read())
    installed, owned = {}, {}
    for pkg in declared:
        version, files = _dpkg(pkg)
        if version is not None:
            installed[pkg], owned[pkg] = version, files
            print(f"{pkg} {version}")
    bad = check(declared, installed, owned, os.path.exists)
    for b in bad:
        print(f"contract-packages: {b}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
