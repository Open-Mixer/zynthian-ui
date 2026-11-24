# -*- coding: utf-8 -*-
#
# A refusal's code is omx-panel's: GESTURES_CODES of its gestures domain (omx-panel 0.16.0, the sorting pass's V4),
# rendered as the `codes` of schema/gestures.json. The engine asks the declaration for each code it refuses with
# (Gestures.code, XY.code) and writes none of them as its own: a code the declaration does not hold is refused by
# name, never recorded.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_engine_plugin_hostd import ph  # noqa: E402,F401  (sets up the stand-ins)
from zyngine import zynthian_panel_gestures as pg  # noqa: E402


def declared():
    try:
        return pg.load_table()
    except OSError as e:
        raise AssertionError(f"omx-panel's gesture declaration is absent ({e}): install omx-panel or set {pg.ENV_TABLE}")


def without(table, code):
    t = copy.deepcopy(table)
    del t["codes"][code]
    return t


def fader(table, readonly=False, default=None):
    travel = pg.Travel({"scale": "linear", "min": 0.0, "max": 1.0}, default, None, table["thresholds"])
    return pg.Gestures("fader", travel, lambda: 0.5, lambda v: None, (0, 0, 400, 50), readonly=readonly, table=table)


def xy(table):
    tx = pg.Travel({"scale": "linear", "min": 0.0, "max": 1.0}, 0.5, None, table["thresholds"])
    return pg.XY(tx, tx, lambda: (0.5, 0.5), lambda x, y: None, (0, 0, 400, 400), table=table)


class RefusalCodesAreTheDeclarations(unittest.TestCase):

    def setUp(self):
        self.table = declared()

    def test_a_read_only_control_is_refused_with_the_declared_code(self):
        g = fader(self.table, readonly=True)
        g.press(10, 10, 0)
        self.assertEqual([r["code"] for r in g.refused], ["GESTURE_READ_ONLY"])
        self.assertIn("GESTURE_READ_ONLY", self.table["codes"])

    def test_a_code_the_declaration_does_not_hold_is_refused_by_name(self):
        for code, act in (("GESTURE_READ_ONLY", lambda t: fader(t, readonly=True).press(10, 10, 0)),
                          ("GESTURE_CONTROL_OWNED", self.owned_xy)):
            with self.subTest(code):
                with self.assertRaisesRegex(KeyError, code):
                    act(without(self.table, code))

    def owned_xy(self, table):
        c = xy(table)
        c.press(10, 10, 0, pid="a")
        c.press(20, 20, 5, pid="b")

    def test_every_code_asked_is_one_the_declaration_holds(self):
        g = fader(self.table)
        for code in self.table["codes"]:
            self.assertEqual(g.code(code), code)
            self.assertEqual(xy(self.table).code(code), code)
        with self.assertRaisesRegex(KeyError, "GESTURE_NOT_DECLARED_HERE"):
            g.code("GESTURE_NOT_DECLARED_HERE")


if __name__ == "__main__":
    unittest.main()
