# -*- coding: utf-8 -*-
#
# An owner's code reads in the device's language (#6): a refusal or a reason plugin-hostd answers with a code is shown
# as the sentence of that code, looked up in its owner's installed catalog through omx-contract's Python catalog
# reader, the English source sentence when the catalog has none; and no Python literal of ours restates an owner's
# source sentence. Read from the installed files: plugin-hostd-protocol's table, the contract directory's vocabularies,
# the owners' catalogs.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT]
if "zyngine" not in sys.modules:
    _pkg = types.ModuleType("zyngine")
    _pkg.__path__ = [os.path.join(ROOT, "zyngine")]
    sys.modules["zyngine"] = _pkg

from zyngine import zynthian_plugin_hostd_protocol as protocol_files  # noqa: E402
from zyngine import zynthian_plugin_hostd_estimate as estimate  # noqa: E402

CONTRACT_DIR = (os.environ.get("OMX_CONTRACT_PATH") or "/usr/share/omx-contract/contract.d").split(":")[0]
CATALOG_ROOT = "/usr/share"
# the files of ours the scan reads: what the fork adds or changes, never upstream Zynthian's own text
OURS = ("zyngine", "zyngui", "zynautoconnect", "zynconf", "tools")


def owner_sources():
    """Every owner code of the contract directory with its English source sentence: {code: (owner, sentence)}."""
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

    root = os.path.join(CONTRACT_DIR, "3")
    for owner in sorted(os.listdir(root)):
        for name in sorted(os.listdir(os.path.join(root, owner))):
            if name.endswith(".json"):
                with open(os.path.join(root, owner, name)) as f:
                    walk(json.load(f), owner)
    return out


def catalog_sentence(owner, key, lang):
    with open(os.path.join(CATALOG_ROOT, owner, "catalogs", "%s.json" % lang)) as f:
        return json.load(f)["messages"].get(key)


def code_keys():
    """{number: code} of plugin-hostd-protocol's table, beside the daemon's protocol file."""
    directory, _ = protocol_files.daemon_file()
    with open(os.path.join(directory, "plugin-hostd-protocol.json")) as f:
        return {r["resp"]: r["code"] for r in json.load(f)["reply_codes"]}


def restated(paths, sources):
    """(file, line, code) of every string literal in `paths` that equals an owner's source sentence."""
    by_sentence = {s: c for c, (_, s) in sources.items()}
    hits = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in by_sentence:
                hits.append((path, node.lineno, by_sentence[node.value]))
    return hits


def our_files():
    for top in OURS:
        for dirpath, _, names in os.walk(os.path.join(ROOT, top)):
            for name in names:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


CATALAN = {"LANG": "ca_ES.UTF-8", "LC_ALL": "", "LC_MESSAGES": "", "LANGUAGE": ""}
ENGLISH = {"LANG": "en_GB.UTF-8", "LC_ALL": "", "LC_MESSAGES": "", "LANGUAGE": ""}
# the reasons the estimate shows for a member, and a refusal of a preset load
CODES = ("reply.plugin-hostd.no-record", "reply.plugin-hostd.no-cell", "reply.plugin-hostd.unknown-plugin",
         "reply.plugin-hostd.preset-plugin-changed")


class test_an_owner_code_reads_in_the_device_language(unittest.TestCase):

    def setUp(self):
        self.sources = owner_sources()
        self.numbers = {v: k for k, v in code_keys().items()}

    def test_in_catalan_a_refusal_is_its_owner_catalog_sentence(self):
        with mock.patch.dict(os.environ, CATALAN):
            p = protocol_files.protocol()
            for key in CODES:
                owner, _ = self.sources[key]
                want = catalog_sentence(owner, key, "ca")
                self.assertTrue(want, "the %s catalog of %s has %s" % ("ca", owner, key))
                self.assertEqual(p.meaning(self.numbers[key]), want, key)

    def test_in_english_it_is_the_owner_source_sentence(self):
        with mock.patch.dict(os.environ, ENGLISH):
            p = protocol_files.protocol()
            for key in CODES:
                self.assertEqual(p.meaning(self.numbers[key]), self.sources[key][1], key)

    def test_the_estimate_gives_a_member_reason_in_the_device_language(self):
        key = "reply.plugin-hostd.no-cell"
        with mock.patch.dict(os.environ, CATALAN):
            self.assertEqual(estimate.reason(self.numbers[key]), catalog_sentence(self.sources[key][0], key, "ca"))


class test_no_literal_restates_an_owner_sentence(unittest.TestCase):

    def test_none_of_ours_does(self):
        files = list(our_files())
        self.assertGreater(len(files), 50, "the scan reads our files")
        self.assertEqual(restated(files, owner_sources()), [])

    def test_sabotage_a_planted_owner_sentence_is_found(self):
        sources = owner_sources()
        code, (_, sentence) = sorted(sources.items())[0]
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("WHY = %r\n" % sentence)
        try:
            self.assertEqual([c for _, _, c in restated([f.name], sources)], [code])
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
