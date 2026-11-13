# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: plugin-hostd protocol (zynthian_plugin_hostd_protocol)
#
# What plugin-hostd declares about its own protocol. Its reply codes (number, name, sentence) and the grammar of a word
# of its lines are its Python client's (plugin_hostd_protocol), which reads the table its package installs; the
# defaults of its configuration are read from the daemon's installed file. Nothing here is typed twice.
# The line the daemon prints when it is ready is read by zynthian-sys's sbin/plugin-hostd-start.sh,
# which starts every plugin-hostd on a Zynthian.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import os
import json
import logging

from plugin_hostd_protocol import Protocol, ProtocolError
from plugin_hostd_protocol import words, quote, encode_path, decode_path, uri_word, pin_key  # noqa: F401

# Where the files are: libplugin-hostd-protocol0 (plugin-hostd 0.16.0 on) installs them in its own directory, the
# daemon's as plugin-hostd.json; plugin-hostd before 0.16.0 installed that one as protocol.json in its directory.
# The first place that holds the daemon's file is the one read.
PLACES = (("/usr/share/plugin-hostd-protocol", "plugin-hostd.json"), ("/usr/share/plugin-hostd", "protocol.json"))
DAEMON_FILES = tuple(name for _, name in PLACES)
HOST_FILE = "mod-host.json"
PROTOCOL_DIR = os.environ.get("ZYNTHIAN_PLUGIN_HOSTD_PROTOCOL_DIR")


def daemon_file(directory=None):
    """(directory, name) of the daemon's protocol file: in the given directory (or ZYNTHIAN_PLUGIN_HOSTD_PROTOCOL_DIR)
    under either name, else the first of PLACES that holds it; the first candidate when none does."""
    directory = directory or PROTOCOL_DIR
    places = [(directory, name) for name in DAEMON_FILES] if directory else list(PLACES)
    for d, name in places:
        if os.path.isfile(os.path.join(d, name)):
            return d, name
    return places[0]


def read(name, directory=None):
    """The JSON file plugin-hostd installs under that name; (contents, None), or ({}, why it is not there)."""
    path = os.path.join(directory or daemon_file()[0], name)
    try:
        with open(path) as f:
            return json.load(f), None
    except (OSError, ValueError) as e:
        return {}, f"plugin-hostd's protocol file {path} is not readable ({e})"


# ---- The words of a line (words, quote), the percent-encoded path of a clap: uri (encode_path, decode_path) and what
# a plugin's uri is as a word and as the key of a pin (uri_word, pin_key) are plugin-hostd's own: its Python client,
# plugin_hostd_protocol (python3-plugin-hostd-protocol), writes them once for every controller. They keep their names
# here for the modules that read them from this one.


def config_default(key, directory=None):
    """The default of a key of plugin-hostd's configuration, from the installed protocol file; None when the file
    or the key is absent."""
    directory, name = daemon_file(directory)
    for entry in read(name, directory)[0].get("config", []):
        if entry.get("key") == key:
            return entry.get("default")
    return None


# ---- The reply codes (#4): the number of a code by its name, its name by its number and its sentence are the client's
# (Protocol: code, name, sentence), read from plugin-hostd-protocol's installed table, the contract directory's
# vocabularies and the owners' catalogs. A code is named as its owner names it: reply.<group>.<reason>.
# mod-host's own names (HOST_FILE) stand for the numbers the table gives no code yet: the engine branches on one of
# them, ERR_INSTANCE_ALREADY_EXISTS (Open-Mixer/omx-clap-core#34), and this read goes when the table has it.


def device_language():
    """The language the device runs in, as its locale names it (LC_ALL, LC_MESSAGES, LANG): ca for ca_ES.UTF-8, en
    for C, POSIX or none."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            lang = value.split(".")[0].split("@")[0].split("_")[0]
            return "en" if lang in ("C", "POSIX", "") else lang
    return "en"


class reply_codes:
    """plugin-hostd's reply codes, as its client reads them once from the installed files.
    needs: the names the caller branches on. A file that is missing or unreadable, or a name no file declares,
    leaves loaded False and failure saying which, logged once as an error here."""

    def __init__(self, needs=(), table=None, directory=None):
        self.client, failure = None, None
        try:
            self.client = Protocol(table=table)
        except (ProtocolError, KeyError, TypeError) as e:
            failure = f"plugin-hostd's protocol table is not usable: {e}"
        host, host_failure = read(HOST_FILE, directory)
        self.host_codes, self.host_names = {}, {}
        for e in host.get("host_errors", []):
            self.host_codes.setdefault(e["name"], e["value"])
            self.host_names.setdefault(e["value"], e["name"])
        missing = [n for n in needs if self.find(n) is None]
        self.failure = failure or host_failure or (
            f"plugin-hostd's protocol files do not declare {', '.join(missing)}" if missing else None)
        self.loaded = self.failure is None
        if self.failure:
            logging.error("%s: the plugin-hostd engine will not start", self.failure)

    def find(self, name):
        """The number a name stands for; None for a name no file declares."""
        if self.client is not None:
            try:
                return self.client.code(name)
            except ProtocolError:
                pass
        return self.host_codes.get(name)

    def code(self, name):
        """The number a name stands for; KeyError for a name no file declares."""
        code = self.find(name)
        if code is None:
            raise KeyError(name)
        return code

    def name(self, code):
        return (self.client.name(code) if self.client is not None else None) or self.host_names.get(code, f"ERR_{-code}")

    def sentence(self, code, lang=None):
        """What an owner's code says to the operator in `lang` (the device's language by default): its owner's catalog
        sentence, else its English source sentence; None for a number no owner code has."""
        if self.client is None:
            return None
        return self.client.sentence(code, lang or device_language()) or self.client.sentence(code)

    def meaning(self, code):
        """What a code says to the operator: its owner's sentence in the device's language, else its name."""
        return self.sentence(code) or self.name(code)
