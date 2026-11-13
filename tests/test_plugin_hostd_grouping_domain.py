# -*- coding: utf-8 -*-
#
# The grouping reasons are plugin-hostd's: its domain plugin-hostd/grouping (contract.d/plugin-hostd/grouping/
# grouping.json) declares the words of PLUGIN_HOSTD_GROUPING_REASONS, each with its description, and the client of its
# protocol gives the same words as constants (GroupingReason), written from that domain. The engine's grouping_text()
# reads the sentences through zynthian_plugin_hostd_grouping and compares a reason with the client's constants, never
# with a word typed here; the old home (grouping.json under the schema major's plugin-hostd directory) is never read.
#
# The domain is the one the installed plugin-hostd-contract carries, in the first contract directory of
# OMX_CONTRACT_PATH that holds it, else /usr/share/omx-contract/contract.d: a run without it fails naming the file.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT]

from tests import plugin_hostd_harness as harness  # noqa: E402

harness.need()
from plugin_hostd_protocol import GroupingReason  # noqa: E402

DIRS = [d for d in (os.environ.get("OMX_CONTRACT_PATH") or "/usr/share/omx-contract/contract.d").split(":") if d]
DOMAIN = next((p for p in (os.path.join(d, "plugin-hostd", "grouping", "grouping.json") for d in DIRS)
               if os.path.isfile(p)), os.path.join(DIRS[0], "plugin-hostd", "grouping", "grouping.json"))


def module():
    """zynthian_plugin_hostd_grouping, loaded fresh (its cache is per module)."""
    spec = importlib.util.spec_from_file_location(
        "grouping_under_test", os.path.join(ROOT, "zyngine", "zynthian_plugin_hostd_grouping.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def installed():
    with open(DOMAIN) as f:
        return json.load(f)


def reasons(doc):
    return {m["const"]: m["description"] for m in doc["components"]["schemas"]["PLUGIN_HOSTD_GROUPING_REASONS"]["oneOf"]}


def contract_dir(doc):
    """A temporary contract directory holding `doc` as the domain plugin-hostd/grouping."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "plugin-hostd", "grouping"))
    with open(os.path.join(d, "plugin-hostd", "grouping", "grouping.json"), "w") as f:
        json.dump(doc, f)
    return d


class TheSentencesAreTheDomains(unittest.TestCase):

    def test_the_installed_domain_is_there(self):
        self.assertTrue(os.path.isfile(DOMAIN), f"{DOMAIN}: plugin-hostd-contract installs the domain plugin-hostd/grouping")

    def test_every_word_of_the_domain_is_told_with_its_sentence(self):
        want = reasons(installed())
        self.assertTrue(want)
        m = module()
        self.assertEqual(m.declared(), want)
        self.assertEqual(m.declared_words(), set(want))
        for word, sentence in want.items():
            if word != GroupingReason.PLAN_REFUSED:
                self.assertEqual(m.text(word), sentence, word)

    def test_the_clients_constants_are_the_domains_words(self):
        # the words compared with are the client's, and they are the words the domain declares: one source
        constants = {v for k, v in vars(GroupingReason).items() if k.isupper()}
        self.assertEqual(constants, set(reasons(installed())))

    def test_a_word_the_domain_drops_is_no_longer_declared(self):
        doc = copy.deepcopy(installed())
        item = doc["components"]["schemas"]["PLUGIN_HOSTD_GROUPING_REASONS"]
        dropped = item["oneOf"].pop(0)["const"]
        m = module()
        d = contract_dir(doc)
        self.assertNotIn(dropped, m.declared(d))
        self.assertEqual(m.declared_words(d), set(reasons(doc)))

    def test_the_first_directory_that_holds_the_domain_is_read(self):
        doc = copy.deepcopy(installed())
        first = doc["components"]["schemas"]["PLUGIN_HOSTD_GROUPING_REASONS"]["oneOf"][0]
        first["description"] = "the sentence of the second directory"
        empty, second = tempfile.mkdtemp(), contract_dir(doc)
        m = module()
        with mock.patch.dict(os.environ, {"OMX_CONTRACT_PATH": f"{empty}:{second}"}):
            self.assertEqual(m.declared()[first["const"]], "the sentence of the second directory")

    def test_the_old_home_is_not_read(self):
        # grouping.json beside the format tables, in the schema major's plugin-hostd directory, as `words`
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "3", "plugin-hostd"))
        with open(os.path.join(d, "3", "plugin-hostd", "grouping.json"), "w") as f:
            json.dump({"PLUGIN_HOSTD_GROUPING_REASONS": {"words": {"refused": {"word": "refused", "doc": "old"}}}}, f)
        m = module()
        self.assertEqual(m.declared(d), {})
        self.assertEqual(m.declared(os.path.join(d, "3", "plugin-hostd")), {})


if __name__ == "__main__":
    unittest.main()
