# -*- coding: utf-8 -*-
#
# Paths this tree no longer carries: each test states the behaviour after the removal.
# Runs with plain `python3 -m unittest`.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class removed_paths(unittest.TestCase):

    def test_there_is_no_tool_that_rewrites_saved_snapshots_from_jalv_to_plugin_hostd(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "tools", "convert_snapshots_to_ph.py")))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "tests", "test_convert_snapshots_to_ph.py")))


if __name__ == "__main__":
    unittest.main()
