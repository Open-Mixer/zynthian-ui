# -*- coding: utf-8 -*-
#
# Stand-ins of the two commands the menus ask, for the tests: `plugin-db query --json <address> <here>` answers with
# one of plugin-db's own golden answers (its tests/golden/*.json, the answers its three readers are held equal on),
# and `plugin-qualify here --json` prints the facts of here those answers were given for. Nothing of an answer is
# written here: a test names the golden case each address answers with.
#
# ZYNTHIAN_PLUGIN_DB_GOLDEN is the golden directory of a plugin-db checkout; without it these tests cannot run and
# say so.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import json
import os
import stat
import sys

GOLDEN = os.environ.get("ZYNTHIAN_PLUGIN_DB_GOLDEN")
if not GOLDEN or not os.path.isfile(os.path.join(GOLDEN, "qualified.json")):
    raise RuntimeError("ZYNTHIAN_PLUGIN_DB_GOLDEN does not name plugin-db's tests/golden directory")

#: the facts of here every golden answer used below was given for, less the rate and the quantum (jackd's)
OWNED = ("machineClass", "hostName", "hostVersion", "hostingEpoch", "rules", "recordSchema")

PLUGIN_DB = '''#!%(python)s -I
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "calls.log"), "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if args[:1] == ["--store"]:
    args = args[2:]
elif args[:1] == ["--system"]:
    args = args[1:]
if args[:2] != ["query", "--json"] or len(args) < 3:
    sys.exit("stub plugin-db: not a query --json")
address, options = args[2], dict(zip(args[3::2], args[4::2]))
with open(os.path.join(here, "answers.json")) as f:
    answers = json.load(f)
if address not in answers:
    sys.stderr.write("plugin-db: no entry %%s\\n" %% address)
    sys.exit(1)
with open(os.path.join(%(golden)r, answers[address] + ".json")) as f:
    case = json.load(f)
want = {"--machine-class": "machineClass", "--host": "hostName", "--host-version": "hostVersion",
        "--hosting-epoch": "hostingEpoch", "--rules": "rules", "--record-schema": "recordSchema"}
for option, key in want.items():
    if options.get(option) != str(case["here"][key]):
        sys.stderr.write("plugin-db: asked with %%s %%s, the case is for %%s\\n" %% (option, options.get(option), case["here"][key]))
        sys.exit(3)
json.dump(case["expect"], sys.stdout)
'''

PLUGIN_QUALIFY = '''#!%(python)s -I
import json, sys
if sys.argv[1:] != ["here", "--json"]:
    sys.exit("stub plugin-qualify: not here --json")
json.dump(%(here)r, sys.stdout)
'''


def golden(name):
    """One of plugin-db's golden cases: its here and the answer its readers give."""
    with open(os.path.join(GOLDEN, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def expect(name):
    return golden(name)["expect"]


def here():
    return {key: golden("qualified")["here"][key] for key in OWNED}


class commands:
    """The two stand-ins in a directory: .plugin_db and .plugin_qualify are their paths, .answers {address: golden
    case} is what plugin-db answers (set() writes it), calls() the command lines plugin-db was run with."""

    def __init__(self, directory, answers=None, here_facts=None):
        self.dir = directory
        self.plugin_db = self.write("plugin-db", PLUGIN_DB % {"python": sys.executable, "golden": GOLDEN})
        self.plugin_qualify = self.write("plugin-qualify", PLUGIN_QUALIFY % {"python": sys.executable,
                                                                             "here": here() if here_facts is None else here_facts})
        self.set(answers or {})

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path

    def set(self, answers):
        self.answers = dict(answers)
        with open(os.path.join(self.dir, "answers.json"), "w") as f:
            json.dump(self.answers, f)

    def calls(self):
        try:
            with open(os.path.join(self.dir, "calls.log")) as f:
                return [json.loads(line) for line in f]
        except OSError:
            return []
