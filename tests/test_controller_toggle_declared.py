#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian GUI -- tests
#
# The controller keeps what the engine said of is_toggle (toggle_declared), apart from the is_toggle two labels make
# (zynthian-ui#86): the drawn widget takes a two-value list for a switch unless the engine said it is no toggle. The real
# controller class, over the stubs the other controller tests use.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT]

for _name in ("pexpect", "pyliblo3", "zynconf", "zynautoconnect", "zyncoder", "zyncoder.zyncore"):
    sys.modules.setdefault(_name, mock.MagicMock())
try:
    import omx_contract.scale  # noqa: F401  (the distro's reader, where it is installed)
except ImportError:  # this test reads no law: the controller only imports the reader
    sys.modules.setdefault("omx_contract", mock.MagicMock())
    sys.modules.setdefault("omx_contract.scale", mock.MagicMock())
if "zyngine" not in sys.modules:
    _pkg = types.ModuleType("zyngine")
    _pkg.__path__ = [os.path.join(ROOT, "zyngine")]
    sys.modules["zyngine"] = _pkg
from zyngine import zynthian_controller as ctrl_mod  # noqa: E402


def controller(**options):
    base = {"labels": ["8 voices", "32 voices"], "ticks": [0, 1], "value": 1, "value_min": 0, "value_max": 1, "is_integer": True}
    base.update(options)
    return ctrl_mod.zynthian_controller(None, "polyphony", base)


class ToggleDeclared(unittest.TestCase):
    def test_an_engine_that_says_no_toggle_is_kept_though_two_labels_make_a_toggle(self):
        z = controller(is_toggle=False)
        self.assertIs(z.toggle_declared, False)
        self.assertTrue(z.is_toggle)  # the stock rule, unchanged

    def test_an_engine_that_says_toggle_is_kept(self):
        self.assertIs(controller(is_toggle=True).toggle_declared, True)

    def test_an_engine_that_says_nothing_leaves_none(self):
        z = controller()
        self.assertIsNone(z.toggle_declared)
        self.assertTrue(z.is_toggle)


if __name__ == "__main__":
    unittest.main()
