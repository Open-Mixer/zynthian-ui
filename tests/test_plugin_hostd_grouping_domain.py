# -*- coding: utf-8 -*-
#
# The grouping reasons' sentences are plugin-hostd's domain plugin-hostd/grouping (plugin-hostd 0.21.0, the sorting
# pass's V17): contract.d/plugin-hostd/grouping/grouping.json, the words its PLUGIN_HOSTD_GROUPING_REASONS item declares,
# each with its description. The engine's grouping_text() reads them through zynthian_plugin_hostd_grouping and no
# other way; the old home (grouping.json under the schema major's plugin-hostd directory, its `words` table) is never
# read again.
#
# The domain is the one the installed plugin-hostd-contract carries, in the contract directory OMX_CONTRACT_PATH names
# first, else /usr/share/omx-contract/contract.d: a run without it fails naming the file, it does not skip.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import copy
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTRACT = (os.environ.get("OMX_CONTRACT_PATH") or "/usr/share/omx-contract/contract.d").split(":")[0]
DOMAIN = os.path.join(CONTRACT, "plugin-hostd", "grouping", "grouping.json")


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
        self.assertTrue(os.path.isfile(DOMAIN), f"{DOMAIN}: plugin-hostd-contract >= 0.21.0 installs the domain plugin-hostd/grouping")

    def test_every_word_of_the_domain_is_told_with_its_sentence(self):
        want = reasons(installed())
        self.assertTrue(want)
        m = module()
        self.assertEqual(m.declared(), want)
        self.assertEqual(m.declared_words(), set(want))
        for word, sentence in want.items():
            if word != m.PLAN_REFUSED:
                self.assertEqual(m.text(word), sentence, word)

    def test_a_word_the_domain_drops_is_no_longer_declared(self):
        doc = copy.deepcopy(installed())
        item = doc["components"]["schemas"]["PLUGIN_HOSTD_GROUPING_REASONS"]
        dropped = item["oneOf"].pop(0)["const"]
        m = module()
        d = contract_dir(doc)
        self.assertNotIn(dropped, m.declared(d))
        self.assertEqual(m.declared_words(d), set(reasons(doc)))

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
