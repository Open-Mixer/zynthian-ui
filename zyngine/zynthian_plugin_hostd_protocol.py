# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: plugin-hostd protocol (zynthian_plugin_hostd_protocol)
#
# What plugin-hostd declares about its own protocol, read from the files its package installs:
# its reply codes and mod-host's and the defaults of its configuration. Nothing here is typed twice: a code is looked
# up by its name, and the grammar of a word of its lines is its Python client's (plugin_hostd_protocol).
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
import importlib.util

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


# ---- An owner's code in the device's language (#6): the sentence of the code in its owner's installed catalog, read
# through omx-contract's Python catalog reader, its English source sentence (the contract directory's vocabulary)
# when the catalog has none. The number of a code is plugin-hostd-protocol's table's; nothing here restates a sentence.

TABLE_FILE = "plugin-hostd-protocol.json"
CONTRACT_DIR = (os.environ.get("OMX_CONTRACT_PATH") or "/usr/share/omx-contract/contract.d").split(":")[0]
CATALOG_READER = os.environ.get("OMX_CONTRACT_CATALOG_PY", "/usr/share/omx-contract/omx_contract_catalog.py")


def device_language():
    """The language the device runs in, as its locale names it (LC_ALL, LC_MESSAGES, LANG): ca for ca_ES.UTF-8, en
    for C, POSIX or none."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            lang = value.split(".")[0].split("@")[0].split("_")[0]
            return "en" if lang in ("C", "POSIX", "") else lang
    return "en"


_reader = []


def catalog_reader():
    """omx-contract's catalog reader, loaded once from where omx-contract installs it; None when it is not there."""
    if not _reader:
        module = None
        try:
            spec = importlib.util.spec_from_file_location("omx_contract_catalog", CATALOG_READER)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except (OSError, ImportError, AttributeError) as e:
            logging.error("omx-contract's catalog reader %s is not readable (%s): codes read in English", CATALOG_READER, e)
            module = None
        _reader.append(module)
    return _reader[0]


def owner_sources(contract_dir=None):
    """Every owner code the contract directory declares with its English source sentence: {code: (owner, sentence)}."""
    out = {}

    def walk(node, owner):
        if isinstance(node, dict):
            text = node.get("text")
            if isinstance(node.get("code"), str) and isinstance(text, dict) and isinstance(text.get("en"), str):
                out.setdefault(node["code"], (owner, text["en"]))
            for v in node.values():
                walk(v, owner)
        elif isinstance(node, list):
            for v in node:
                walk(v, owner)

    root = os.path.join(contract_dir or CONTRACT_DIR, "3")
    for owner in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        for name in sorted(os.listdir(os.path.join(root, owner))):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(root, owner, name)) as f:
                        walk(json.load(f), owner)
                except (OSError, ValueError):
                    continue
    return out


class protocol:
    """plugin-hostd's codes by name and by number, read once from both files.
    needs: the names the caller branches on. A file that is missing or unreadable, or a name neither file
    declares, leaves loaded False and failure saying which, logged once as an error here."""

    def __init__(self, directory=None, needs=()):
        directory, name = daemon_file(directory)
        (daemon, daemon_failure), (host, host_failure) = (read(n, directory) for n in (name, HOST_FILE))
        self.codes = {}  # name => code
        self.names = {}  # code => name, the first name a code has
        self.meanings = {}  # code => what the code means, as plugin-hostd's protocol file says it
        # mod-host's codes, then the ones plugin-hostd adds
        for e in host.get("host_errors", []):
            self.codes.setdefault(e["name"], e["value"])
            self.names.setdefault(e["value"], e["name"])
        for e in daemon.get("errors", []):
            self.codes[e["name"]] = e["code"]
            self.names[e["code"]] = e["name"]
            if e.get("meaning"):
                self.meanings[e["code"]] = e["meaning"]
        # each number's owner code (reply.<group>.<reason>), and each code's owner and source sentence
        table, _ = read(TABLE_FILE, directory)
        self.keys = {r["resp"]: r["code"] for r in table.get("reply_codes", [])}
        self.sources = owner_sources()
        missing = [n for n in needs if n not in self.codes]
        self.failure = daemon_failure or host_failure or (
            f"plugin-hostd's protocol files in {directory} do not declare {', '.join(missing)}"
            if missing else None)
        self.loaded = self.failure is None
        if self.failure:
            logging.error("%s: the plugin-hostd engine will not start", self.failure)

    def code(self, name):
        """The number a name stands for; KeyError for a name the protocol does not declare."""
        return self.codes[name]

    def name(self, code):
        return self.names.get(code, f"ERR_{-code}")

    def sentence(self, code, lang=None):
        """What an owner's code says to the operator in `lang` (the device's language by default): its owner's catalog
        sentence, else its English source sentence; None for a number no owner code has."""
        owner, source = self.sources.get(self.keys.get(code), (None, None))
        if source is None:
            return None
        lang = lang or device_language()
        reader = catalog_reader() if lang != "en" else None
        if reader is None:
            return source
        key = reader.code_key(self.keys[code])
        return reader.sentence_of(reader.load_catalog(owner, lang), key, source)

    def meaning(self, code):
        """What a code says to the operator: its owner's sentence in the device's language (sentence), else what the
        protocol file says it means, else its name."""
        return self.sentence(code) or self.meanings.get(code) or self.name(code)
