# -*- coding: utf-8 -*-
#
# The fork's bar control and its two-dimensional one answer the one gesture vocabulary (zynthian-ui#42): the drawbar
# widget (setBfree's and any LV2 organ's drawbars) as a `bar` group, the XY screen as an `xy`. omx-panel's own parity
# scripts for setBfree's drawbars (a sweep, a tap, a double-tap; its test/fixtures/gestures/scripts.json, beside the
# declaration this tree reads, never copied) are driven into the group, and the widget and the screen are driven
# through their own Tk handlers.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import json
import os
import sys
import importlib
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_engine_plugin_hostd import ROOT  # noqa: E402  (sets up the stand-ins)
from zyngine import zynthian_panel_gestures as pg  # noqa: E402


def omx_panel(*path):
    """A file of the omx-panel tree whose schema/gestures.json is read."""
    return os.path.join(os.path.dirname(os.path.dirname(pg.table_path())), *path)


def omx_panel_scripts():
    """omx-panel's parity scripts."""
    with open(omx_panel("test", "fixtures", "gestures", "scripts.json")) as f:
        return json.load(f)["scripts"]


SETBFREE = [s for s in omx_panel_scripts() if s["name"].startswith("setBfree")]


class Column:
    """One drawbar: its declared travel and default, and its value."""

    def __init__(self, travel, start):
        self.travel = {k: travel[k] for k in ("scale", "min", "max", "step") if k in travel}
        self.default = travel.get("default")
        self.value = start if start is not None else (self.default if self.default is not None else travel["min"])


def bar_group(script, on_word=None):
    """The script's bars, from the descriptor it names (omx-panel's), each starting where the script says, else at its
    declared default."""
    c = script["control"]
    g = c["geometry"]
    with open(omx_panel(script["descriptor"])) as f:
        declared = {x["symbol"]: x["travel"] for x in json.load(f)["controls"] if "travel" in x and "symbol" in x}
    cols = {s: Column(declared[s], c["start"].get(s)) for s in c["symbols"]}
    bars = [(pg.Travel(cols[s].travel, cols[s].default), (lambda s=s: cols[s].value),
             (lambda v, s=s: setattr(cols[s], "value", v)), (i * g["pitch"], 0, g["w"], g["h"]))
            for i, s in enumerate(c["symbols"])]
    return pg.BarGroup(bars, on_word=on_word), cols


def drive(group, script):
    for e in script["script"]:
        if e["type"] == "down":
            group.press(e["x"], e["y"], e["t"], e["id"], e["ptype"])
        elif e["type"] == "move":
            group.motion(e["x"], e["y"], e["t"], e["id"])
        else:
            group.release(e["x"], e["y"], e["t"], e["id"])


class SetBfreeParity(unittest.TestCase):
    def test_the_three_scripts_are_there(self):
        self.assertEqual(len(SETBFREE), 3, [s["name"] for s in SETBFREE])

    def test_each_script_lands_where_omx_panel_says(self):
        for script in SETBFREE:
            with self.subTest(script["name"]):
                words = []
                group, cols = bar_group(script, on_word=lambda word, symbol=None: words.append((word, symbol)))
                drive(group, script)
                want = script["expect"]
                symbols = script["control"]["symbols"]
                for s, v in want["value"].items():
                    if want["tolerance"] == "exact":
                        self.assertEqual(cols[s].value, v, s)
                    else:
                        self.assertLessEqual(abs(cols[s].value - v), 1, s)
                self.assertEqual(group.log[-1]["word"], want["word"])
                if "gestures" in want:
                    self.assertEqual(len(group.log), want["gestures"])
                if "selected" in want:
                    self.assertIn(("select", symbols.index(want["selected"])), words)


class Axis:
    def __init__(self, lo, hi, default):
        self.value_min, self.value_max, self.value_default, self.value = lo, hi, default, default
        self.ticks, self.is_toggle, self.is_integer, self.position_law = None, False, False, None

    def set_value(self, v, send=True):
        self.value = v


class XYVocabulary(unittest.TestCase):
    def setUp(self):
        self.x, self.y, self.words = Axis(0.0, 100.0, 50.0), Axis(0.0, 100.0, 50.0), []
        self.xy = pg.XY(pg.Travel.of(self.x), pg.Travel.of(self.y), lambda: (self.x.value, self.y.value),
                        lambda xv, yv: (self.x.set_value(xv), self.y.set_value(yv)), (0, 0, 400, 200),
                        on_word=self.words.append)

    def test_a_drag_moves_both_axes_from_where_the_threshold_was_crossed(self):
        dz = pg.load_table()["thresholds"]["dragStartPx"]
        self.xy.press(100, 100, 0)
        self.xy.motion(100 + dz + 1, 100 + dz + 1, 10)
        self.xy.motion(100 + dz + 1 + 40, 100 + dz + 1 + 20, 20)
        self.xy.release(100 + dz + 1 + 40, 100 + dz + 1 + 20, 30)
        self.assertAlmostEqual(self.x.value, 60.0)  # 40 of 400 px
        self.assertAlmostEqual(self.y.value, 60.0)  # 20 of 200 px, the screen's y grows downward
        self.assertEqual(self.xy.log[-1]["word"], "drag")

    def test_fine_is_the_declared_ratio_of_a_drag(self):
        r = pg.load_table()["thresholds"]["fineRatio"]
        self.xy.press(100, 100, 0)
        self.xy.motion(115, 100, 10, fine=True)
        self.xy.motion(155, 100, 20, fine=True)
        self.xy.release(155, 100, 30)
        self.assertAlmostEqual(self.x.value, 50.0 + 10.0 * r)
        self.assertEqual(self.xy.log[-1]["word"], "fine")

    def test_a_double_tap_resets_both_axes_and_a_tap_selects(self):
        self.x.value, self.y.value = 10.0, 90.0
        self.xy.press(100, 100, 0)
        self.xy.release(100, 100, 50)
        self.assertEqual((self.x.value, self.y.value), (10.0, 90.0))
        self.assertEqual(self.words, ["select"])
        self.xy.press(100, 100, 100)
        self.xy.release(100, 100, 150)
        self.assertEqual((self.x.value, self.y.value), (50.0, 50.0))
        self.assertEqual(self.xy.log[-1]["word"], "reset")

    def test_a_long_press_is_more_and_moves_nothing(self):
        T = pg.load_table()["timings"]["longPressMs"]["default"]
        self.xy.press(100, 100, 0)
        self.xy.tick(T)
        self.xy.release(100, 100, T + 10)
        self.assertEqual(self.words, ["more"])
        self.assertEqual((self.x.value, self.y.value), (50.0, 50.0))

    def test_the_arrows_step_their_axis(self):
        self.xy.key("Right", 0)
        self.xy.key("Down", 1000, shift=True)
        self.assertAlmostEqual(self.x.value, 51.0)
        self.assertAlmostEqual(self.y.value, 55.0)  # Down grows y, as the screen draws it
        self.assertEqual([g["word"] for g in self.xy.log], ["step", "step"])


class TheForkSaysWhatItHas(unittest.TestCase):
    def test_the_header_names_the_bar_and_the_xy(self):
        with open(os.path.join(ROOT, "zyngine", "zynthian_panel_gestures.py")) as f:
            head = f.read().split("import json", 1)[0]
        self.assertNotIn("draw none", head)
        self.assertNotIn("no control of it is two-dimensional", head)
        self.assertIn("zynthian_widget_drawbar", head)
        self.assertIn("zynthian_gui_control_xy", head)


def _import_screens():
    """The drawbar widget and the XY screen subclass Tk classes: stand-ins for the import only (CI's debian:trixie has
    no tkinter), taken out again so the other test files see what they saw before; their handlers are the real ones."""
    names = ("tkinter", "tkinter.font", "zyngui", "zyngui.zynthian_gui_config", "zyngui.zynthian_widget_base",
             "zyngui.zynthian_gui_fullscreen_modal", "zyngui.zynthian_widget_drawbar", "zyngui.zynthian_gui_control_xy")
    saved = {n: sys.modules.get(n) for n in names}
    tk = types.ModuleType("tkinter")
    tk.Canvas = tk.Frame = type("Tk", (), {})
    tk.font = types.ModuleType("tkinter.font")
    gui = types.ModuleType("zyngui")
    gui.__path__ = [os.path.join(ROOT, "zyngui")]
    base = types.ModuleType("zyngui.zynthian_widget_base")
    base.zynthian_widget_base = type("zynthian_widget_base", (), {})
    modal = types.ModuleType("zyngui.zynthian_gui_fullscreen_modal")
    modal.zynthian_gui_fullscreen_modal = type("zynthian_gui_fullscreen_modal", (), {})
    sys.modules.update({"tkinter": tk, "tkinter.font": tk.font, "zyngui": gui, "zyngui.zynthian_gui_config": mock.MagicMock(),
                        "zyngui.zynthian_widget_base": base, "zyngui.zynthian_gui_fullscreen_modal": modal})
    gui.zynthian_gui_config, gui.zynthian_widget_base, gui.zynthian_gui_fullscreen_modal = (
        sys.modules["zyngui.zynthian_gui_config"], base, modal)
    try:
        return (importlib.import_module("zyngui.zynthian_widget_drawbar").zynthian_widget_drawbar,
                importlib.import_module("zyngui.zynthian_gui_control_xy").zynthian_gui_control_xy)
    finally:
        for n, m in saved.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m


DRAWBAR, XY_SCREEN = _import_screens()


class TheWidgetAndTheScreenGoThroughIt(unittest.TestCase):
    """The upstream drawbar widget's own Tk handlers drive the group (its drawing untouched)."""

    def test_the_drawbar_widget_paints_through_the_group(self):
        W = DRAWBAR
        ctrls = {f"db{i}": types.SimpleNamespace(value=8 if i < 2 else 0, value_default=8, value_min=0, value_max=8,
                                                 ticks=None, drawbar=True) for i in range(9)}
        for c in ctrls.values():
            c.set_value = (lambda v, c=c: setattr(c, "value", v))
        w = W.__new__(W)
        w.processor = types.SimpleNamespace(controllers_dict=ctrls)
        w.drawbars, w.width, w.height, w.border = list(ctrls), 9 * 24 + 4, 160, 2
        w.gestures, w._gestures_for = None, None
        ev = lambda x, y, t: types.SimpleNamespace(x=x, y=y, time=t, state=0)  # noqa: E731
        col = (w.width - 2 * w.border) // 9
        # down in db0, then across db1..db3 near the bottom: the widget's bars come out downward, so the bottom is 8
        w.on_press(ev(w.border + col // 2, 80, 0))
        w.on_motion(ev(w.border + col // 2, 95, 10))
        w.on_motion(ev(w.border + col * 3 + col // 2, 159, 20))
        w.on_release(ev(w.border + col * 3 + col // 2, 159, 30))
        self.assertEqual([ctrls[f"db{i}"].value for i in range(4)], [5, 6, 7, 8])  # the columns jumped over take the line between
        self.assertEqual(w.gestures.log[-1]["word"], "paint")

    def test_the_xy_screen_drags_and_resets_through_the_xy(self):
        S = XY_SCREEN
        zx, zy = Axis(0.0, 100.0, 50.0), Axis(0.0, 100.0, 50.0)
        zx.name, zy.name = "x", "y"
        s = S.__new__(S)
        s.zyngui = types.SimpleNamespace(state_manager=types.SimpleNamespace(zctrl_x=zx, zctrl_y=zy), cuia_back=lambda: None)
        s.x0, s.y0, s.width, s.height, s.gestures = 24, 18, 400, 200, None
        s.get_controller_values = lambda: None
        s.canvas = types.SimpleNamespace(itemconfig=lambda *a, **k: None)
        s.text_x = s.text_y = None
        ev = lambda x, y, t: types.SimpleNamespace(x=x, y=y, time=t, state=0)  # noqa: E731
        s.cb_press(ev(100, 100, 0))
        s.cb_canvas(ev(120, 100, 10))
        s.cb_canvas(ev(160, 100, 20))
        s.cb_release(ev(160, 100, 30))
        self.assertAlmostEqual(zx.value, 60.0)
        s.cb_press(ev(100, 100, 100))
        s.cb_release(ev(100, 100, 120))
        s.cb_press(ev(100, 100, 200))
        s.cb_release(ev(100, 100, 220))
        self.assertEqual((zx.value, zy.value), (50.0, 50.0))
        self.assertEqual(s.gestures.log[-1]["word"], "reset")

    def test_the_xy_screen_says_it_is_left_by_a_long_press(self):
        # the screen's hint is upstream's "Tap 3 times to exit", the old job of a tap: on the vocabulary a double-tap
        # resets and a long press (more) leaves, so the hint says the long press
        hint = XY_SCREEN.__init__.__globals__.get("EXIT_HINT", "Tap 3 times to exit")  # the module, as the stand-ins left it
        self.assertIn("long press", hint.lower())
        self.assertNotIn("tap", hint.lower())


if __name__ == "__main__":
    unittest.main()
