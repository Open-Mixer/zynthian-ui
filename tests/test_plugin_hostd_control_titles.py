# -*- coding: utf-8 -*-
#
# The title of a plugin-hostd controller: its label, then its unit's symbol as the contract writes it. plugin-hostd's
# param_info and a descriptor's travel give the unit as the contract's WORD (omx-contract-data's param domain,
# PARAM_UNITS: `none`, `percent`, `dBPerOct`), and the screen showed that word: "Input none", "Mix percent", "Slope
# dBPerOct". The word is shown as its `x-symbol` ("", "%", "dB/oct"), verbatim. And the controller's title is never
# camel-split: zynthian_gui_controller splits a title at each lower-to-upper change for an LV2 symbol such as
# "CutoffFreq", which cut the symbol dB into "d B" ("Trim d B"); omx-panel's labels are words already.
# tests/fixtures/contract_dir/param/param.json is the file omx-contract-data 0.24.1 installs, byte for byte.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT]
FIXTURE = os.path.join(HERE, "fixtures", "contract_dir")

from test_engine_plugin_hostd import ph  # noqa: E402
from zyngine.zynthian_controller import zynthian_controller  # noqa: E402


def load_gui_controller():
    """zyngui/zynthian_gui_controller.py over a stand-in Tk: the title it would draw, recorded."""
    config = mock.MagicMock(font_family="Audiowide", font_size=16, ui_look="stock")  # what the module reads at import
    modules = {"zyngui": types.ModuleType("zyngui"), "zyngui.zynthian_gui_config": config, "tkinter": mock.MagicMock(Canvas=type("Canvas", (), {})),
               "tkinter.font": mock.MagicMock()}
    modules["zyngui"].__path__ = []
    modules["zyngui"].zynthian_gui_config = config
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("gui_controller_under_test",
                                                      os.path.join(ROOT, "zyngui", "zynthian_gui_controller.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class unit_symbols(unittest.TestCase):

    def setUp(self):
        os.environ["OMX_CONTRACT_PATH"] = FIXTURE
        self.addCleanup(os.environ.pop, "OMX_CONTRACT_PATH", None)
        ph.unit_symbols.cache_clear()

    def test_a_unit_word_is_shown_as_its_symbol(self):
        self.assertEqual([ph.unit_symbol(w) for w in ("none", "percent", "dBPerOct", "dB", "Hz", "ms")],
                         ["", "%", "dB/oct", "dB", "Hz", "ms"])

    def test_no_unit_is_no_text(self):
        for word in (None, "", "-", "unknown", "none"):
            self.assertEqual(ph.unit_symbol(word), "", word)

    def test_the_title_is_the_label_and_the_symbol(self):
        self.assertEqual(ph.control_title("Input", "none"), "Input")
        self.assertEqual(ph.control_title("Trim", "dB"), "Trim dB")
        self.assertEqual(ph.control_title("Comp Mix", "percent"), "Comp Mix %")
        self.assertEqual(ph.control_title("HPF Slope", "dBPerOct"), "HPF Slope dB/oct")
        self.assertNotIn("none", ph.control_title("EQ Bands", "none"))

    def test_a_word_the_contract_does_not_list_is_shown_as_it_is(self):
        self.assertEqual(ph.unit_symbol("furlongs"), "furlongs")


class titles_are_not_camel_split(unittest.TestCase):

    def drawn_title(self, zctrl, title):
        module = load_gui_controller()
        drawn = []
        ctrl = types.SimpleNamespace(hidden=False, zctrl=zctrl, label_title=1, title_width=100, title_height=20,
                                     itemconfigure=lambda obj, text, font: drawn.append(text))
        ctrl.set_text = lambda *a, **k: module.zynthian_gui_controller.set_text(ctrl, *a, **k)
        with mock.patch.object(module, "get_cached_font_size", return_value=12), mock.patch.object(module, "tkFont"):
            module.zynthian_gui_controller.set_title(ctrl, title)
        return drawn[-1]

    def test_a_plugin_hostd_title_keeps_its_unit_symbol_whole(self):
        z = zynthian_controller(None, "1", {"name": "Trim dB", "camel_title": False})
        self.assertEqual(self.drawn_title(z, z.short_name), "Trim dB")
        self.assertNotIn("d B", self.drawn_title(z, "Gate Threshold dB"))

    def test_any_other_title_is_split_as_upstream_does(self):
        z = zynthian_controller(None, "CutoffFreq", {"name": "CutoffFreq"})
        self.assertEqual(self.drawn_title(z, z.short_name), "Cutoff Freq")


if __name__ == "__main__":
    unittest.main()
