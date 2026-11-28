# -*- coding: utf-8 -*-
#
# A delay's taps reach omx-panel's renderer: its time_response display has no point, only the taps plugin-hostd answers
# after the count ('stems ...'), and the panel widget gives them to the view (omx_panel_view_set_stems) on the refresh
# that gives it the values. Before, the widget handed the view the points alone, so the delay's frame was drawn empty
# while omx-panel's own picture drew the taps (omx-panel's renderer, reference picture of omx-delay).
#
# The widget is the real file (tests/test_control_blank_slot_panel.load_widget); the engine and the view are stand-ins.
#
# Copyright (C) 2026 Pau Aliagas
# SPDX-License-Identifier: GPL-2.0-or-later

import types
import unittest

from tests.test_control_blank_slot_panel import load_widget

TAPS = [(0.0, -4.44, 1.0, " "), (250.0, -7.96, 1.0, "L"), (500.0, -13.98, 0.538, "R")]


class View:
    """The renderer's view as the refresh uses it: what it was given."""

    def __init__(self):
        self.meters, self.curves, self.stems, self.drew = [], {}, {}, 0

    def set_value(self, *a): pass
    def set_choice(self, *a): pass
    def set_curve(self, k, points): self.curves[k] = points
    def set_stems(self, k, stems): self.stems[k] = stems


class TapsReachTheView(unittest.TestCase):

    def refresh(self, drawing):
        module = load_widget()
        w = object.__new__(module.zynthian_widget_omx_panel)
        view = View()
        w.drawn, w.drawn_page, w.drawn_state, w.controls, w.meter_at = view, (), None, [], {}
        w.display_map = {0: 2}  # the screen's display 0 is the description's display 2
        w.page_keys = lambda: []
        w.paint = lambda v: setattr(v, "drew", v.drew + 1)
        w.panel_image = w.spectrum = None  # no measured spectrum under the display
        asked = []
        w.processor = types.SimpleNamespace(engine=types.SimpleNamespace(
            curve_drawing=lambda d: (asked.append(d), drawing)[1], meter=lambda symbol: None))
        self.assertTrue(w.refresh_drawn())
        self.assertEqual(asked, [2], "the description's display is asked")
        return view

    def test_a_delays_taps_are_given_to_the_view(self):
        view = self.refresh(([], TAPS))
        self.assertEqual(view.stems, {0: TAPS}, "the taps, on the screen's display")
        self.assertEqual(view.curves, {}, "and no curve: a delay has no point")
        self.assertEqual(view.drew, 1)

    def test_a_curve_with_no_taps_sets_none(self):
        points = [(20.0, 0.0), (20000.0, 0.0)]
        view = self.refresh((points, None))
        self.assertEqual(view.curves, {0: points})
        self.assertEqual(view.stems, {}, "a reply with no taps leaves the view's taps alone")


if __name__ == "__main__":
    unittest.main()
