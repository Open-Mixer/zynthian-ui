# -*- coding: utf-8 -*-
#
# The panel widget joins its controllers to the layout's controls by the layout's `param` (#47). omx-panel's layout
# (`describe --layout`) names a CLAP control by the symbol its parameter contract states (omx-comp's threshold is
# thresholdDb) and carries the parameter's number as `param`; plugin-hostd's controllers are keyed by that number ("0").
# Keyed as p<number>, no controller of a contracted plugin bound: the renderer drew every knob at its minimum, every
# value box blank, a page's part empty (omx-comp on Zynthian, 2026-11-28). The layout below is omx-panel 0.17's for
# omx-comp's first four controls, as `describe --layout` prints it.
#
# The widget, the real panel view's screen_part and the real gestures are this tree's; tkinter, the widget's base and
# the renderer's view are stand-ins (tests/test_control_blank_slot_panel.py's).
#
# Copyright (C) 2026 Pau Aliagas
# SPDX-License-Identifier: GPL-2.0-or-later

import types
import unittest
from unittest import mock

from tests.test_control_blank_slot_panel import Controller, load_widget

LAYOUT = {
    "sections": [{"key": "comp", "label": "Comp"}, {"key": "key", "label": "Key"}],
    "controls": [
        {"symbol": "thresholdDb", "param": 0, "section": 0, "widget": "knob"},
        {"symbol": "ratio", "param": 1, "section": 0, "widget": "knob"},
        {"symbol": "kneeDb", "param": 2, "section": 0, "widget": "knob"},
        {"symbol": "keyHpHz", "param": 10, "section": 1, "widget": "knob"},
    ],
    "displays": [],
    "meters": [],
}


class View:
    """The renderer's view: its controls are the part's, in order, by the layout's symbol (omx_panel_view_symbol)."""
    opened = []

    def __init__(self, part, look=None):
        self.symbols = [c["symbol"] for c in part["controls"]]
        self.meters, self.values, self.travels = [], {}, {}
        View.opened.append(self)

    def set_title(self, *a): pass
    def set_surface(self, *a): pass
    def close(self): pass

    def set_travel(self, i, lo, hi, *a):
        self.travels[self.symbols[i]] = (lo, hi)

    def set_value(self, i, fraction, text):
        self.values[self.symbols[i]] = (round(fraction, 3), text)

    def draw(self, w, h):
        return bytes(w * h * 4), None


class JoinByParam(unittest.TestCase):

    def setUp(self):
        self.module = load_widget()
        for module, name, value in ((self.module.panel_view, "View", View),
                                    (self.module.ui_look, "look_for", lambda *a: None),
                                    (self.module.panel_image, "PanelImage", mock.MagicMock())):
            patch = mock.patch.object(module, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        # plugin-hostd's controllers of a CLAP plugin: keyed by the parameter's number, as the daemon sets it
        self.zctrls = {}
        for number, value in (("0", -18.0), ("1", 4.0), ("2", 6.0), ("10", 80.0)):
            z = Controller(number, None)
            z.value_min, z.value_max = (-60.0, 0.0) if number == "0" else (0.0, 100.0)
            z.value = value
            self.zctrls[number] = z
        engine = types.SimpleNamespace(drawn=(LAYOUT, {}), zctrls=self.zctrls, name="omx comp",
                                       curve=lambda display: [], meter=lambda symbol: None)
        widget = object.__new__(self.module.zynthian_widget_omx_panel)
        widget.processor = types.SimpleNamespace(engine=engine)
        widget.zyngui_control = types.SimpleNamespace(zcontrollers=[self.zctrls["0"], self.zctrls["1"],
                                                                    self.zctrls["2"], None])
        widget.width, widget.height, widget.stopped, widget.shown = 400, 240, None, False
        widget.drawn = widget.drawn_state = widget.panel_image = widget.spectrum = None
        widget.widget_canvas = mock.MagicMock()
        self.widget = widget

    def test_every_control_of_the_page_binds_to_its_controller_by_param(self):
        View.opened = []
        self.assertTrue(self.widget.build_drawn())
        view = self.widget.drawn
        self.assertEqual(view.symbols, ["thresholdDb", "ratio", "kneeDb"], "the page's section, and not the key's")
        self.assertEqual([(view.symbols[i], z.symbol) for i, z in self.widget.controls],
                         [("thresholdDb", "0"), ("ratio", "1"), ("kneeDb", "2")])
        self.widget.refresh_drawn()
        self.assertEqual(view.values, {"thresholdDb": (0.7, "-18.0"), "ratio": (0.04, "4.0"), "kneeDb": (0.06, "6.0")},
                         "each knob at its controller's value, each value box its text")

    def test_the_part_is_the_section_of_the_page_controls(self):
        self.assertEqual(sorted(self.widget.page_keys()), ["kneeDb", "ratio", "thresholdDb"])
        self.widget.zyngui_control.zcontrollers = [self.zctrls["10"], None, None, None]
        self.assertTrue(self.widget.build_drawn())
        self.assertEqual(self.widget.drawn.symbols, ["keyHpHz"])
        self.assertEqual([z.symbol for _, z in self.widget.controls], ["10"])

    def test_a_layout_with_no_param_keeps_the_p_number_key(self):
        """An LV2 control is keyed by its port symbol, and a layout of no `param` names a CLAP control p<number>."""
        self.assertEqual(self.module.engine_key("0", {}), "p0")
        self.assertEqual(self.module.engine_key("cutoff", {"0": "thresholdDb"}), "cutoff")
        self.assertEqual(self.module.engine_key("0", {"0": "thresholdDb"}), "thresholdDb")


if __name__ == "__main__":
    unittest.main()
