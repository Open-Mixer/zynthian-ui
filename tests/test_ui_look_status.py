# -*- coding: utf-8 -*-
#
# The status icon at the top right of every screen (the heart, or the refresh arrow when an update is available) takes its
# colour from the CPU load. Stock is upstream's: a gradient from a bright green (0, 0xCC, 0) through yellow to red, written
# in zynthian_gui_base.refresh_status. Under the vintage look the colour follows the look's meter roles instead
# (zynthian-ui#87): green below 50 %, green to amber to 75 %, amber to red to 100 %, the three colours the look table
# (zyngine/zynthian_ui_look.py) already takes from zynthian_gui_config, never a colour typed in the screen.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import importlib.util
import os
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


look = load("zynthian_ui_look_status", os.path.join(ROOT, "zyngine", "zynthian_ui_look.py"))

GREEN, AMBER, RED = "#34d17b", "#f2b632", "#ff5a4d"


def colours(**kw):
    return types.SimpleNamespace(ui_look="vintage", color_midi=GREEN, color_alt2=AMBER, color_error=RED, **kw)


def mix(a, b, t):
    ca, cb = [tuple(int(c[k:k + 2], 16) for k in (1, 3, 5)) for c in (a, b)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


class CpuColour(unittest.TestCase):

    def test_stock_keeps_upstreams_gradient(self):
        self.assertIsNone(look.cpu_colour(types.SimpleNamespace(ui_look="stock"), 10))
        self.assertIsNone(look.cpu_colour(types.SimpleNamespace(ui_look="stock"), 99))

    def test_a_light_load_is_the_meter_green(self):
        for load in (0, 10, 49.9, 50):
            self.assertEqual(look.cpu_colour(colours(), load), GREEN, load)

    def test_three_quarters_is_the_amber_and_a_full_load_the_red(self):
        self.assertEqual(look.cpu_colour(colours(), 75), AMBER)
        self.assertEqual(look.cpu_colour(colours(), 100), RED)

    def test_between_the_stops_it_is_the_mix_of_the_two_neighbours(self):
        self.assertEqual(look.cpu_colour(colours(), 62.5), mix(GREEN, AMBER, 0.5))
        self.assertEqual(look.cpu_colour(colours(), 87.5), mix(AMBER, RED, 0.5))

    def test_each_stop_is_its_own_role(self):
        # a look with three other colours: each stop follows its role, so a wrong mapping fails by name
        other = types.SimpleNamespace(ui_look="vintage", color_midi="#010203", color_alt2="#0a0b0c", color_error="#a0b0c0")
        self.assertEqual(look.cpu_colour(other, 0), "#010203")
        self.assertEqual(look.cpu_colour(other, 75), "#0a0b0c")
        self.assertEqual(look.cpu_colour(other, 100), "#a0b0c0")

    def test_the_roles_are_the_look_tables_meter_roles(self):
        roles = dict(look.ROLES)
        self.assertEqual((roles["--meter-green"], roles["--meter-amber"], roles["--meter-red"]), ("color_midi", "color_alt2", "color_error"))

    def test_a_load_off_the_scale_is_held_to_it(self):
        self.assertEqual(look.cpu_colour(colours(), -5), GREEN)
        self.assertEqual(look.cpu_colour(colours(), 250), RED)


class StatusScreen(unittest.TestCase):
    """zynthian_gui_base.refresh_status: stock's gradient is untouched, and the look's colour is asked for under a look."""

    def setUp(self):
        with open(os.path.join(ROOT, "zyngui", "zynthian_gui_base.py")) as f:
            self.tree = ast.parse(f.read())
        self.refresh = next(n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef) and n.name == "refresh_status")
        self.src = ast.unparse(self.refresh)

    def test_the_icon_asks_the_look_for_its_colour_under_a_look(self):
        calls = [n for n in ast.walk(self.refresh) if isinstance(n, ast.Call) and ast.unparse(n.func) == "ui_look.cpu_colour"]
        self.assertEqual(len(calls), 1, "refresh_status asks zyngine.zynthian_ui_look.cpu_colour for the icon's colour")
        self.assertIn("zynthian_gui_config.ui_look", self.src, "and only under a look: stock draws upstream's gradient")

    def test_stock_gradient_is_still_upstreams(self):
        # each line of upstream's gradient, as often as upstream writes it (0xCC is 204): an edit of any one is seen
        for piece, times in (("cr = 0", 1), ("cg = 204", 2), ("cr = 204", 1), ("cr = int((cpu_load - 50) * 204 / 25)", 1),
                             ("cg = int((100 - cpu_load) * 204 / 25)", 1), ("if cpu_load < 50", 1), ("elif cpu_load < 75", 1)):
            self.assertEqual(self.src.count(piece), times, piece)

    def test_the_module_imports_the_look(self):
        imported = [ast.unparse(n) for n in self.tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertIn("from zyngine import zynthian_ui_look as ui_look", imported)


if __name__ == "__main__":
    unittest.main()
