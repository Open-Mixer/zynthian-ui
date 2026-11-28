# -*- coding: utf-8 -*-
#
# omx-contract's contract directory as the owners install it (Open-Mixer/zynthian-ui#139): it has no schema-major level
# (omx-contract docs/contract-dir.md, the owner's ruling of 2026-11-25), so plugin-hostd-contract 0.22.1 installs
# <contractdir>/plugin-hostd/grouping/grouping.json and omx-dsp-contract 0.34.3 <contractdir>/omx-dsp/primitives/curve.json.
# tests/fixtures/contract_dir holds those two files byte for byte as the two debs of the staging channel install them,
# and OMX_CONTRACT_PATH names it, as it names any contract directory to the house readers. A reader that still appends a
# major (contract.d/3/...) finds nothing there: the grouping reasons lose their sentences and no display is a curve.
# The last case refuses a digit (or a glob standing for one) as a level of any contract path the fork writes.
# Plain `python3 -m unittest` or pytest.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import json
import os
import re
import subprocess
import sys
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

from zyngine import zynthian_contract_dir as contract_dir  # noqa: E402
from zyngine import zynthian_plugin_hostd_grouping as grouping  # noqa: E402
from zyngine import zynthian_omx_panel_view as view  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "contract_dir")
GROUPING = os.path.join(FIXTURE, "plugin-hostd", "grouping", "grouping.json")


def owner_words():
    """{word: sentence} as the fixture's domain plugin-hostd/grouping declares them, read here from the file itself."""
    with open(GROUPING) as f:
        doc = json.load(f)
    return {w["const"]: w.get("x-text") or w["description"]
            for w in doc["components"]["schemas"]["PLUGIN_HOSTD_GROUPING_REASONS"]["oneOf"]}


class contract_dir_case(unittest.TestCase):

    def setUp(self):
        patch = mock.patch.dict(os.environ, {"OMX_CONTRACT_PATH": FIXTURE + ":/nowhere"})
        patch.start()
        self.addCleanup(patch.stop)
        grouping._declared.clear()
        view._curve_words.clear()
        self.addCleanup(grouping._declared.clear)
        self.addCleanup(view._curve_words.clear)


class test_the_grouping_reasons_from_the_installed_layout(contract_dir_case):

    def test_every_reason_word_reads_as_its_owners_sentence(self):
        words = owner_words()
        self.assertEqual(len(words), 16)
        self.assertEqual(grouping.declared(), words)
        for word, sentence in words.items():
            if word != grouping.PLAN_REFUSED:
                self.assertEqual(grouping.text(word), sentence, word)
                self.assertFalse(grouping.text(word).startswith("Not grouped: "), word)

    def test_the_declared_words_are_the_domains(self):
        self.assertEqual(grouping.declared_words(), set(owner_words()))

    def test_a_directory_without_the_domain_declares_nothing(self):
        self.assertIsNone(grouping.declared_words("/nonexistent"))
        self.assertEqual(grouping.declared("/nonexistent"), {})


class test_the_curve_words_from_the_installed_layout(contract_dir_case):

    def test_the_kinds_and_roles_are_omx_dsps(self):
        kinds, roles = view.curve_words()
        self.assertIn("eq_response", kinds)
        self.assertIn("transfer_curve", kinds)
        self.assertIn("knee_start", roles)


class test_the_contract_directory_is_found_as_the_house_readers_find_it(unittest.TestCase):

    def test_the_environment_names_it_first(self):
        with mock.patch.dict(os.environ, {"OMX_CONTRACT_PATH": "/a::/b"}):
            self.assertEqual(contract_dir.contract_dirs(), ["/a", "/b"])

    def test_else_the_installed_protocol_client_or_pkg_config_names_it(self):
        env = {k: v for k, v in os.environ.items() if k != "OMX_CONTRACT_PATH"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(contract_dir, "_installed_dirs", return_value=[]), \
                mock.patch.object(contract_dir, "_pkg_config", return_value="/pc/contract.d") as pc:
            self.assertEqual(contract_dir.contract_dirs(), ["/pc/contract.d"])
            pc.assert_called_once_with("--variable=contractdir", "omx-contract")
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(contract_dir, "_installed_dirs", return_value=["/installed/contract.d"]):
            self.assertEqual(contract_dir.contract_dirs(), ["/installed/contract.d"])

    def test_a_domain_is_its_last_segments_document(self):
        self.assertEqual(contract_dir.domain("plugin-hostd/grouping", dirs=["/nowhere", FIXTURE]), GROUPING)
        self.assertIsNone(contract_dir.domain("plugin-hostd/history", dirs=[FIXTURE]))


# ---- no contract path the fork writes carries a schema-major level

# a level of a contract path that is a number, or the glob that stood for one
MAJOR_LEVEL = re.compile(r"(?:^|/)contract\.d/(?:[0-9]+|\*)(?:/|$)")
SCANNED = (".py", ".sh", ".yml", ".yaml", ".md", ".txt", ".json")


def tracked():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def literal_paths(source):
    """(line, path) of every string constant, and of every os.path.join whose arguments include constants, each
    argument that is not a constant standing as one segment ('<>')."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "join" and \
                isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "path":
            parts = [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else "<>" for a in node.args]
            yield node.lineno, "/".join(parts)
            # a join that names a digit level under a root it was given (root, "3", "omx-dsp", ...)
            for a, b in zip(parts, parts[1:]):
                if a == "<>" and re.fullmatch(r"[0-9]+", b):
                    yield node.lineno, "contract.d/" + "/".join(parts[parts.index(b):])


class test_no_contract_path_carries_a_major_level(unittest.TestCase):

    def test_no_file_and_no_literal_names_a_digit_level(self):
        found = []
        for rel in tracked():
            if MAJOR_LEVEL.search(rel):
                found.append("%s: a tracked path under a major level" % rel)
            if not rel.endswith(SCANNED) or not os.path.isfile(os.path.join(ROOT, rel)):
                continue
            with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
                text = f.read()
            try:
                literals = list(literal_paths(text)) if rel.endswith(".py") else None
            except SyntaxError:  # a template that is Python once filled in (@@NAME@@): read as text
                literals = None
            if literals is not None:
                for line, path in literals:
                    if MAJOR_LEVEL.search(path):
                        found.append("%s:%d: %r" % (rel, line, path))
            else:
                for n, line in enumerate(text.splitlines(), 1):
                    if MAJOR_LEVEL.search(line.replace("\\", "/")):
                        found.append("%s:%d: %s" % (rel, n, line.strip()))
        self.assertEqual(found, [], "the contract directory has no schema-major level (#139):\n" + "\n".join(found))

    def test_the_check_sees_each_spelling_it_refuses(self):
        # the refused spellings are written with {m} for the level, so that this file itself names none
        for source in ('P = "/usr/share/omx-contract/contract.d/{m}/plugin-hostd"\n'.format(m="3"),
                       'G = "omx-contract/contract.d/{m}/" + owner\n'.format(m="*"),
                       'import os\np = os.path.join(root, "{m}", "omx-dsp", "primitives", "curve.json")\n'.format(m="3"),
                       'import os\np = os.path.join(c, "omx-contract", "contract.d", "{m}", "plugin-hostd")\n'.format(m="3")):
            self.assertTrue(any(MAJOR_LEVEL.search(p) for _, p in literal_paths(source)), source)
        for source in ('P = "/usr/share/omx-contract/contract.d/plugin-hostd/grouping"\n',
                       'import os\np = os.path.join(root, "omx-dsp", "primitives", "curve.json")\n'):
            self.assertFalse(any(MAJOR_LEVEL.search(p) for _, p in literal_paths(source)), source)


if __name__ == "__main__":
    unittest.main()
