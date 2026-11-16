# -*- coding: utf-8 -*-
#
# Paths this tree no longer carries: each test states the behaviour after the removal.
# Runs with plain `python3 -m unittest`.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import sys
import json
import tempfile
import importlib.util
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class removed_paths(unittest.TestCase):

    def test_there_is_no_tool_that_rewrites_saved_snapshots_from_jalv_to_plugin_hostd(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "tools", "convert_snapshots_to_ph.py")))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "tests", "test_convert_snapshots_to_ph.py")))

    def test_the_engine_config_holds_no_plugin_hostd_entry_for_a_later_load_to_throw_away(self):
        """The PH entries are made from the jalv ones at every load, so they are not saved with the engine config."""
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"ZYNTHIAN_CONFIG_DIR": tmp, "ZYNTHIAN_SYS_DIR": tmp}), \
                mock.patch.dict(sys.modules, {"lilv": mock.MagicMock(), "rdflib": mock.MagicMock()}):
            spec = importlib.util.spec_from_file_location("lv2_under_test", os.path.join(ROOT, "zyngine", "zynthian_lv2.py"))
            lv2 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(lv2)
            lv2.engines = {"JV/Amp": {"TYPE": "Audio Effect"}, "PH/Amp": {"TYPE": "Audio Effect"},
                           "PH/clap:/usr/lib/clap/a.clap#a": {"TYPE": "MIDI Synth"}, "ZY": {"TYPE": "MIDI Synth"}}
            lv2.save_engines()
            with open(os.path.join(tmp, "engine_config.json")) as f:
                saved = json.load(f)
        self.assertEqual(sorted(saved), ["JV/Amp", "ZY"])


if __name__ == "__main__":
    unittest.main()
