# -*- coding: utf-8 -*-
#
# A control page with a blank slot (zynthian-ui#52): plugin-hostd's pages are omx-panel's as they come, and a slot
# omx-panel leaves empty (a meter, a display, a hidden or read-only control, the rest of a short page) stays, blank:
# the processor builds it as None (zynthian_processor.build_ctrl_screen, the engine's blank_slots). The control screen
# lists every such page and opens it: its list reads a page's group from a control it holds, never from slot 0, and
# its screen type skips the blank slots. The screen's own fill_list and get_screen_type run; tkinter, the base screens
# and the selector's drawing are stand-ins, the processor is the real one.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import sys
import types
import logging
import unittest
import importlib.util
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT]
for _name in ("zynconf", "zynautoconnect", "zyncoder", "zyncoder.zyncore"):  # the Zynthian's native libraries
    sys.modules.setdefault(_name, mock.MagicMock())
if "zyngine" not in sys.modules:
    _pkg = types.ModuleType("zyngine")
    _pkg.__path__ = [os.path.join(ROOT, "zyngine")]
    sys.modules["zyngine"] = _pkg
from zyngine.zynthian_processor import zynthian_processor  # noqa: E402


def stand_in(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


class selector:
    def __init__(self, *args, **kwargs):
        pass

    def fill_list(self):
        pass


def load_control():
    """zyngui/zynthian_gui_control.py, the screen's own code."""
    gui_config = stand_in("zyngui.zynthian_gui_config")
    modules = {
        "zyngui": stand_in("zyngui", __path__=[], zynthian_gui_config=gui_config),
        "zyngui.zynthian_gui_config": gui_config,
        "zyngui.zynthian_gui_base": stand_in("zyngui.zynthian_gui_base", zynthian_gui_base=object),
        "zyngui.zynthian_gui_selector": stand_in("zyngui.zynthian_gui_selector", zynthian_gui_selector=selector),
        "zyngui.zynthian_gui_controller": stand_in("zyngui.zynthian_gui_controller", zynthian_gui_controller=object),
        "zyngine.zynthian_signal_manager": stand_in("zyngine.zynthian_signal_manager", zynsigman=mock.MagicMock()),
    }
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("zynthian_gui_control_under_test",
                                                      os.path.join(ROOT, "zyngui", "zynthian_gui_control.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module.zynthian_gui_control


class zctrl:
    """A control as the screen reads it: its group, and no file path."""

    def __init__(self, symbol, group):
        self.symbol, self.group_symbol, self.short_name = symbol, group, symbol
        self.is_path, self.path_file_types = False, None


def processor(pages):
    """A real processor whose engine keeps blank slots (plugin-hostd's), its screens built from <pages>: [(name, [key
    or None])]."""
    proc = object.__new__(zynthian_processor)
    proc.engine = types.SimpleNamespace(name="omx eq8", blank_slots=True, _ctrl_screens=pages)
    proc.controllers_dict = {k: zctrl(k, name.split()[0].lower()) for name, keys in pages for k in keys if k}
    proc.current_screen_index, proc.chain = -1, None
    with mock.patch("zyngine.zynthian_processor.zynsigman", mock.MagicMock(), create=True):
        proc.init_ctrl_screens()
    return proc


# omx eq8's HPF group as the Pi showed it: five controls, the second page holding one, after a blank slot
PAGES = [("HPF", ["hpf_on", "hpf_freq", "hpf_q", "hpf_slope"]), ("HPF 2", [None, "hpf_mix", None, None]),
         ("Meters", [None, None, None, None])]


class ShortPages(unittest.TestCase):
    def setUp(self):
        self.proc = processor(PAGES)
        screen = object.__new__(load_control())
        screen.zyngui = mock.MagicMock()
        screen.zyngui.get_current_processor.return_value = self.proc
        screen.configure_processors = lambda curproc: setattr(screen, "processors", [self.proc])
        screen.index = 0
        self.screen = screen

    def test_the_processor_keeps_the_blank_slot(self):
        """The page as the screen gets it: slot 0 blank (the seam this test stands on)."""
        self.assertIsNone(self.proc.get_ctrl_screen("HPF 2")[0])

    def test_every_page_is_listed(self):
        """A page whose slot 0 is blank is listed, and so is a page with no control at all, each selectable."""
        # the screen's own refusal, never another test's daemon thread logging meanwhile
        with self.assertLogs(level=logging.ERROR) as logs:
            self.screen.fill_list()
            logging.error("fill_list returned")
        self.assertEqual([m for m in logs.output if "control page" in m], [])
        pages = [row for row in self.screen.list_data if row[0] is not None]
        self.assertEqual([row[2] for row in pages], ["HPF", "HPF 2", "Meters"])
        self.assertEqual([row[4] for row in pages], [0, 1, 2], "the page indices the processor's screens are kept by")
        self.assertEqual(pages[1][0], "hpf", "the group of the control the page holds")

    def test_a_page_with_a_blank_slot_opens(self):
        """Its screen type is read over the controls it holds, past the blank slots."""
        for name, _ in PAGES:
            with self.subTest(page=name):
                self.screen.zcontrollers = self.proc.get_ctrl_screen(name)
                self.screen.screen_type = None
                self.assertIsNone(self.screen.get_screen_type())

    def test_a_file_control_after_a_blank_slot_is_found(self):
        """A file control behind a blank slot still gives the page its audio-file screen."""
        wav = zctrl("sample", "hpf")
        wav.is_path, wav.path_file_types = True, ["wav"]
        self.screen.zcontrollers = [None, wav, None, None]
        self.screen.screen_type = None
        self.assertEqual((self.screen.get_screen_type(), self.screen.widget_zctrl), ("audio_file", wav))


if __name__ == "__main__":
    unittest.main()
