# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: plugin qualification (zynthian_plugin_qualification)
#
# What plugin-db answers about a plugin on this machine. Nothing is read, judged or worded here: the answer is
# plugin-db's reader's (python3-plugin-db, `plugin-db query --json <address> <here>`), a dict of the words of its
# vocabulary:
#
#   state    unqualified, qualified, isolated-only, conditions-unmet, refused, absent
#   runs     shared, alone, not-loaded
#   reason   why, a word with its sentence in the device's language (plugin_db.why)
#   source   none, local, reference
#   tier     in-process, isolated, or None: the answering record's, never worked out here
#   figures  None, or the latency in ms at this rate and quantum, the line and where it stands against it
#            (within, over, unmeasured)
#
# The facts of here (the machine class, the host and its version, the hosting epoch, the rules, the record schema)
# are plugin-qualify's constants: `plugin-qualify here --json` prints them, and the rate and the quantum are jackd's.
# The store is plugin-db's own (PLUGIN_DB_STORE, else the system one, else the user's); plugin-qualify's sync fills
# it.
#
# A row is addressed as plugin-db addresses it: lv2:<uri> for an LV2 plugin, clap:<id> for a CLAP one (our URL of a
# CLAP plugin is clap:<path>#<id>).
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import json
import logging
import subprocess

import plugin_db
from plugin_db.query import COMMAND

HERE_COMMAND = "plugin-qualify"


class HereError(Exception):
    """the facts of here could not be read: no answer can be asked for"""


def address(url):
    """plugin-db's address of one of our plugin URLs; None for a URL that is no plugin's."""
    if not url:
        return None
    if url.startswith("clap:"):
        ident = url.rsplit("#", 1)[-1] if "#" in url else url[5:]
        return f"clap:{ident}" if ident else None
    return f"lv2:{url}"


def here_facts(command=HERE_COMMAND):
    """The facts of here plugin-qualify owns, as `plugin-qualify here --json` prints them. HereError when it can't."""
    try:
        r = subprocess.run([command, "here", "--json"], capture_output=True, text=True)
    except OSError as e:
        raise HereError(f"{command} here --json => {e}")
    if r.returncode:
        raise HereError(f"{command} here --json exits {r.returncode}: {r.stderr.strip()}")
    try:
        facts = json.loads(r.stdout)
    except ValueError as e:
        raise HereError(f"{command} here --json does not print JSON => {e}")
    if not isinstance(facts, dict):
        raise HereError(f"{command} here --json does not print an object")
    return facts


class qualification:
    """The answers of plugin-db's reader, here. One command run per plugin, rate and quantum, kept until refresh()."""

    def __init__(self, store=None, command=COMMAND, here_command=HERE_COMMAND):
        self.store = store
        self.command = command
        self.here_command = here_command
        self.here = None
        self.answers = {}

    def refresh(self):
        """Forget what was answered: the next answer is asked again. Returns self."""
        self.here = None
        self.answers = {}
        return self

    def answer(self, url, rate=None, quantum=None):
        """plugin-db's answer for the plugin of one of our URLs at this rate and quantum; None for a URL that is no
        plugin's and for an entry the command can't answer for (logged). HereError when the facts of here can't be
        read: then nothing can be asked."""
        target = address(url)
        if target is None:
            return None
        if self.here is None:
            self.here = here_facts(self.here_command)
        key = (target, rate, quantum)
        if key not in self.answers:
            try:
                self.answers[key] = plugin_db.query(target, {**self.here, "rate": rate, "quantum": quantum},
                                                    store=self.store, command=self.command)
            except (plugin_db.QueryError, OSError, ValueError) as e:
                logging.debug(f"plugin-db has no answer for {target} => {e}")
                self.answers[key] = None
        return self.answers[key]
