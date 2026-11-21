# -*- coding: utf-8 -*-
#
# The vintage controller drawn with Tk and PIL (docs/ui-look-tk-widgets.md, zynthian-ui#93 stage 1).
# `vintage` is Zynthian's own drawing: a PIL face per size, cached, with Tk canvas items for what moves; the renderer
# of omx-panel is not asked for anything. The module is zyngui/zynthian_gui_controller_tk.py; the config, the stock
# controller and that module are the real files over a canvas that records its items and the thread of every call;
# PIL is real (the Pi has it; CI installs python3-pil).
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import math
import os
import re
import sys
import threading
import types
import unittest
from unittest import mock

from tests.test_ui_look_widgets import (CONFIG, CONTROLLER, ROOT, STOCK, VINTAGE, Canvas, Font, Zctrl, config_under,
                                        load_module)

try:
    from PIL import Image, ImageColor
except ImportError:  # the Pi has PIL, CI installs it
    Image = None

TK = os.path.join(ROOT, "zyngui", "zynthian_gui_controller_tk.py")
CI = os.environ.get("CI") == "true"

# the knob's metal as the vintage preset carries it (zynthian-sys config/ui-looks/openmixer-vintage.sh)
KNOB = {"ZYNTHIAN_UI_COLOR_KNOB_FACE": "#8f98a2", "ZYNTHIAN_UI_COLOR_KNOB_EDGE": "#1d2227",
        "ZYNTHIAN_UI_COLOR_KNOB_CAP_HI": "#dde3e9", "ZYNTHIAN_UI_COLOR_KNOB_KNURL": "#4f5963",
        "ZYNTHIAN_UI_COLOR_KNOB_POINTER": "#e8732c", "ZYNTHIAN_UI_COLOR_SWITCH_TRACK": "#2a323d",
        "ZYNTHIAN_UI_COLOR_SWITCH_THUMB": "#c7ced6"}
TOKEN_ENV = sorted(KNOB)
LOOK = {**VINTAGE, **KNOB}


def rgb(colour):
    return ImageColor.getrgb(colour)[:3]


class TkCanvas(Canvas):
    """The recording canvas, with the items the Tk look draws, and the thread of every call that touches it."""

    def __init__(self, parent=None, **kw):
        super().__init__(parent, **kw)
        self.threads = []

    def _item(self, kind, *xy, **kw):
        self.threads.append(threading.get_ident())
        return super()._item(kind, *xy, **kw)

    def create_line(self, *xy, **kw): return self._item("line", *xy, **kw)
    def create_oval(self, *xy, **kw): return self._item("oval", *xy, **kw)

    def itemconfig(self, item, **kw):
        self.threads.append(threading.get_ident())
        super().itemconfig(item, **kw)

    itemconfigure = itemconfig

    def coords(self, item, *xy):
        self.threads.append(threading.get_ident())
        super().coords(item, *xy)

    def delete(self, item):
        self.threads.append(threading.get_ident())
        super().delete(item)

    def tag_lower(self, item, below=None):
        for i in self._ids(item):
            self.order.remove(i)
            self.order.insert(0, i)


def load_tk_controller(environ):
    """zyngui.zynthian_gui_controller as zynthian_gui.py imports it under <environ>: the class the module exports, the
    config, and sys.modules as loaded. Tk is the recording canvas; no renderer is stubbed because none is asked for."""
    values = config_under(environ)
    config = types.ModuleType("zyngui.zynthian_gui_config")
    config.__dict__.update({k: v for k, v in values.items() if k != "said"}, font_family="sans", font_size=12,
                           layout={"ctrl_orientation": "horizontal"}, ctrl_graph=1, num_zynpots=0, select_ctrl=3,
                           zyngui=mock.MagicMock())
    config.zyngui.chain_manager.get_midi_learn_from_zctrl.return_value = None
    gui = types.ModuleType("zyngui")
    gui.__path__ = [os.path.join(ROOT, "zyngui")]
    gui.zynthian_gui_config = config
    engine = types.ModuleType("zyngine")
    engine.__path__ = [os.path.join(ROOT, "zyngine")]
    law = types.ModuleType("zyngine.zynthian_position_law")
    law.scale_position = lambda law, value: 0.5
    tk = types.ModuleType("tkinter")
    tk.Canvas, tk.ARC, tk.CENTER, tk.LEFT, tk.S, tk.NW, tk.NORMAL, tk.HIDDEN, tk.FLAT, tk.ROUND = (
        TkCanvas, "arc", "center", "left", "s", "nw", "normal", "hidden", "flat", "round")
    tkfont = types.ModuleType("tkinter.font")
    tkfont.Font = Font
    tk.font = tkfont
    zyncoder, zyncore = types.ModuleType("zyncoder"), types.ModuleType("zyncoder.zyncore")
    zyncore.lib_zyncore = mock.MagicMock()
    modules = {"tkinter": tk, "tkinter.font": tkfont, "zyngui": gui, "zyngui.zynthian_gui_config": config,
               "zyngine": engine, "zyngine.zynthian_position_law": law, "zyncoder": zyncoder, "zyncoder.zyncore": zyncore}
    with mock.patch.dict(sys.modules, modules):
        for name in [m for m in sys.modules if m.startswith("zyngui.zynthian_gui_controller_") or m in
                     ("zyngine.zynthian_panel_gestures", "zyngine.zynthian_ui_look", "zyngine.zynthian_omx_panel_view")]:
            del sys.modules[name]
        module = load_module("zynthian_gui_controller_tk_under_test", CONTROLLER)
        loaded = dict(sys.modules)
    return module.zynthian_gui_controller, config, loaded


@unittest.skipUnless(Image, "no PIL")
class TkControllerCase(unittest.TestCase):
    environ = LOOK

    def setUp(self):
        self.cls, self.config, self.loaded = load_tk_controller(self.environ)
        self.images = []
        test = self

        class Recorded(self.cls):
            def photo_of(self, image):
                test.images.append(image)
                return ("photo", image.size)

        self.Recorded = Recorded
        self.tkmod = self.loaded["zyngui.zynthian_gui_controller_tk"]
        self.tkmod.FACES.clear()
        self.tkmod.BUILDS.clear()

    def controller(self, zctrl, w=256, h=176, **kw):
        ctrl = self.Recorded(0, None, zctrl, **kw)
        ctrl._w, ctrl._h = w, h
        ctrl.on_size(None)
        ctrl.plot_value()
        return ctrl

    def line_of(self, ctrl, colour):
        return [o for o in ctrl.items.values() if o["kind"] == "line" and o.get("fill") == colour]


class TheTokensAndTheRefusal(unittest.TestCase):
    def test_the_config_reads_each_knob_token_from_its_variable(self):
        values = config_under(LOOK)
        self.assertEqual(values["ui_look"], "vintage")
        for env in TOKEN_ENV:
            self.assertEqual(values["color_" + env.replace("ZYNTHIAN_UI_COLOR_", "").lower()], KNOB[env], env)

    def test_a_preset_short_of_any_token_is_refused_by_name_and_draws_stock_with_no_default_filled_in(self):
        for env in TOKEN_ENV:
            short = {k: v for k, v in LOOK.items() if k != env}
            values = config_under(short)
            self.assertEqual(values["ui_look"], "stock", env)
            self.assertTrue(any(env in str(s) for s in values["said"]), (env, values["said"]))
            self.assertIsNone(values["color_" + env.replace("ZYNTHIAN_UI_COLOR_", "").lower()], f"{env} got a default")

    def test_an_empty_token_is_an_unset_one(self):
        values = config_under({**LOOK, "ZYNTHIAN_UI_COLOR_KNOB_EDGE": ""})
        self.assertEqual(values["ui_look"], "stock")

    def test_stock_reads_no_token_and_says_nothing(self):
        values = config_under(STOCK)
        self.assertEqual((values["ui_look"], values["said"]), ("stock", []))


class TheOneSwitchRule(unittest.TestCase):
    def setUp(self):
        _, _, loaded = load_tk_controller(LOOK)
        self.tk = loaded["zyngui.zynthian_gui_controller_tk"]
        self.gestures = loaded["zyngine.zynthian_panel_gestures"]

    CASES = [dict(ticks=[0, 1], labels=["off", "on"], is_toggle=True, toggle_declared=True),
             dict(ticks=[0, 1], labels=["8 voices", "32 voices"], is_toggle=True, toggle_declared=False),
             dict(ticks=[0, 127], labels=["off", "on"], is_toggle=True, toggle_declared=None),
             dict(ticks=[0, 1, 2], labels=["a", "b", "c"]), dict(), dict(is_path=True)]

    def test_the_drawing_and_the_gesture_table_name_the_same_kind_for_every_control(self):
        for kw in self.CASES:
            z = Zctrl(**kw)
            gesture = self.gestures.widget_of(z)
            drawn = self.tk.widget_kind(z, False)
            self.assertEqual(drawn, {"switch": "switch", "selector": "selector", "fader": "knob"}[gesture]
                             if not z.is_path else "display", kw)

    def test_a_two_value_list_the_engine_says_is_no_toggle_is_a_selector_in_both(self):
        z = Zctrl(**self.CASES[1])
        self.assertEqual(self.gestures.widget_of(z), "selector")
        self.assertEqual(self.tk.widget_kind(z, False), "selector")

    def test_a_path_and_a_selector_counter_are_displays(self):
        self.assertEqual(self.tk.widget_kind(Zctrl(is_path=True), False), "display")
        self.assertEqual(self.tk.widget_kind(Zctrl(), True), "display")

    def test_the_drawing_has_no_rule_of_its_own(self):
        text = open(TK).read()
        self.assertIn("widget_of", text)
        self.assertNotIn("toggle_declared", text, "the rule is the gesture module's alone")


class TheKnob(TkControllerCase):
    def test_a_knob_is_one_face_image_and_three_pointer_lines_under_the_text(self):
        ctrl = self.controller(Zctrl(value=0.25))
        self.assertEqual(len(ctrl.of("image")), 1)
        self.assertEqual(len(self.line_of(ctrl, self.config.color_knob_pointer)), 1)
        self.assertEqual(len([o for o in ctrl.of("line")]), 3)
        for item in (ctrl.label_title, ctrl.value_text, ctrl.midi_bind, ctrl.graph_pickup):
            for ours in ctrl.of("image") + ctrl.of("line"):
                self.assertGreater(ctrl.order.index(item), ctrl.order.index(next(i for i, o in ctrl.items.items() if o is ours)))

    def test_the_stock_arc_is_not_shown(self):
        ctrl = self.controller(Zctrl())
        self.assertEqual(ctrl.items[ctrl.graph]["state"], "hidden")
        ctrl.show()
        self.assertEqual(ctrl.items[ctrl.graph]["state"], "hidden")
        self.assertEqual(ctrl.items[ctrl.value_text]["state"], "normal")

    def test_the_face_is_the_arcs_box_two_radii_square_and_opaque(self):
        ctrl = self.controller(Zctrl())
        self.assertEqual(self.images[-1].size, (168, 168))  # 256 x 176: radius 176 // 2 - 4 = 84
        self.assertEqual(self.images[-1].mode, "RGB")

    def test_a_new_value_moves_the_pointer_and_makes_no_image(self):
        ctrl = self.controller(Zctrl(value=0.25))
        images, built = len(self.images), len(self.tkmod.BUILDS)
        pointer = self.line_of(ctrl, self.config.color_knob_pointer)[0]
        before = pointer["coords"]
        face = ctrl.of("image")[0]
        cx, cy = face["coords"][0] + 84, face["coords"][1] + 84
        for value in (0.0, 0.25, 0.5, 1.0):
            ctrl.zctrl.value = value
            ctrl.calculate_plot_values()
            ctrl.plot_value()
            x1, y1, x2, y2 = pointer["coords"]
            angle = math.degrees(math.atan2(x2 - cx, cy - y2))  # clockwise from 12 o'clock
            self.assertAlmostEqual(angle, -135 + 270 * value if value < 1 else 135, delta=1.0, msg=str(value))
            self.assertAlmostEqual(math.hypot(x1 - cx, y1 - cy), 0.21 * 84, delta=1.0)
            self.assertAlmostEqual(math.hypot(x2 - cx, y2 - cy), 0.63 * 84, delta=1.0)
        self.assertNotEqual(pointer["coords"], before)
        self.assertEqual((len(self.images), len(self.tkmod.BUILDS)), (images, built), "a value makes no image and no face")
        self.assertEqual(len(ctrl.of("image")), 1)

    def test_a_bipolar_control_points_up_at_zero_and_shows_its_zero_tick_in_the_on_colour(self):
        ctrl = self.controller(Zctrl(value=0.0, value_min=-1.0, value_max=1.0, value_default=0.0))
        ctrl.calculate_plot_values()
        ctrl.plot_value()
        pointer = self.line_of(ctrl, self.config.color_knob_pointer)[0]
        x1, y1, x2, y2 = pointer["coords"]
        self.assertAlmostEqual(x2, x1, delta=1.0)
        self.assertLess(y2, y1)
        self.assertEqual(len(self.line_of(ctrl, self.config.color_on)), 1)
        # a unipolar one has none
        other = self.controller(Zctrl())
        self.assertEqual(self.line_of(other, self.config.color_on), [])

    def test_the_pickup_marker_rides_the_knobs_travel_outside_its_rim(self):
        ctrl = self.controller(Zctrl(value=0.25))
        ctrl.pickup = True
        ctrl.zynpot_abs(0.5)
        marker = ctrl.items[ctrl.graph_pickup]
        self.assertEqual(marker["state"], "normal")
        self.assertAlmostEqual(marker["start"], 90 + 135 - 270 * 0.5 - 6, delta=0.01)
        self.assertEqual(marker["extent"], 12)
        x1, y1, x2, y2 = marker["coords"]
        self.assertGreater((x2 - x1) / 2, 0.97 * 84)  # outside the tick ring's radius

    def test_the_selection_is_a_frame_none_when_unselected_and_readonly_takes_the_off_colour(self):
        ctrl = self.controller(Zctrl())
        frames = lambda: [o["outline"] for o in ctrl.of("rectangle") if o.get("outline") and o["state"] == "normal"]
        self.assertEqual(frames(), [])
        ctrl.set_hl()
        self.assertEqual(frames(), [self.config.color_hl])
        ctrl.unset_hl()
        self.assertEqual(frames(), [])
        ctrl.set_color_readonly()
        self.assertEqual(frames(), [self.config.color_ctrl_bg_off])

    def test_a_hidden_controller_draws_nothing_and_a_blank_slot_shows_none_of_the_last_face(self):
        self.Recorded(0, None, Zctrl(), hidden=True)
        self.assertEqual(self.images, [])
        ctrl = self.controller(Zctrl())
        ctrl.config(None)
        ctrl.show()
        self.assertEqual(ctrl.of("image") + ctrl.of("line"), [])
        ctrl.config(Zctrl(symbol="resonance"))
        ctrl.show()
        self.assertEqual(len(ctrl.of("image")), 1)

    def test_the_face_is_built_once_per_size_and_token_set(self):
        a, b = self.controller(Zctrl()), self.controller(Zctrl(value=0.9))
        self.assertEqual(len(self.tkmod.BUILDS), 1, self.tkmod.BUILDS)
        self.controller(Zctrl(), w=200, h=120)
        self.assertEqual(len(self.tkmod.BUILDS), 2)
        a.on_size(None)  # a resize event to the same size builds nothing
        self.assertEqual(len(self.tkmod.BUILDS), 2)
        self.assertEqual(len(a.of("image")), 1, "the old face does not pile up")

    def test_the_renderer_is_not_asked_for_anything(self):
        self.assertNotIn("zyngine.zynthian_omx_panel_view", self.loaded)
        self.assertNotIn("zyngine.zynthian_ui_look", self.loaded)
        self.assertNotIn("zyngui.zynthian_gui_controller_drawn", self.loaded)


class TheOtherKinds(TkControllerCase):
    def switch(self, value):
        return self.controller(Zctrl(ticks=[0, 1], labels=["Off", "On"], value=value, is_toggle=True))

    def test_a_switch_is_a_pill_and_a_thumb_and_a_value_moves_items_only(self):
        ctrl = self.switch(0)
        self.assertEqual(ctrl.of("image"), [])
        self.assertEqual(len(ctrl.of("oval")), 3, "two caps and the thumb")
        thumb = next(o for o in ctrl.of("oval") if o.get("fill") == self.config.color_switch_thumb)
        track = [o for o in ctrl.items.values() if o["kind"] in ("oval", "rectangle") and o.get("fill") in
                 (self.config.color_switch_track, self.config.color_on)]
        off = thumb["coords"]
        self.assertTrue(all(o["fill"] == self.config.color_switch_track for o in track))
        ctrl.zctrl.value = 1
        ctrl.calculate_plot_values()
        ctrl.plot_value()
        self.assertGreater(thumb["coords"][0], off[0], "the thumb is at the right when on")
        self.assertTrue(all(o["fill"] == self.config.color_on for o in track), "the track takes the on colour")
        self.assertEqual(self.images, [])

    def test_a_selector_is_a_strip_with_the_chosen_segment_moved_by_coords(self):
        ctrl = self.controller(Zctrl(ticks=[0, 1, 2, 3], labels=["Sine", "Saw", "Square", "Noise"], value=0))
        self.assertEqual(len(ctrl.of("polygon")), 1)
        chosen = [o for o in ctrl.of("rectangle") if o.get("fill") == self.config.color_on]
        self.assertEqual(len(chosen), 1)
        seen = []
        for value in (0, 1, 2, 3):
            ctrl.zctrl.value = value
            ctrl.calculate_plot_values()
            ctrl.plot_value()
            seen.append(chosen[0]["coords"][0])
        self.assertEqual(seen, sorted(set(seen)), "the segment steps right")
        self.assertEqual(self.images, [])
        self.assertEqual(ctrl.items[ctrl.value_text]["text"], "Noise")

    def test_a_display_is_a_cached_glass_with_the_value_in_the_on_colour(self):
        ctrl = self.controller(Zctrl(is_path=True, value="/zynthian/media/take 3.wav"))
        self.assertEqual(len(ctrl.of("image")), 1)
        self.assertEqual(ctrl.items[ctrl.value_text]["fill"], self.config.color_on)
        self.assertEqual(ctrl.items[ctrl.value_text]["text"], "take 3.wav")
        n = len(self.images)
        ctrl.zctrl.value = "/zynthian/media/take 4.wav"
        ctrl.calculate_plot_values()
        ctrl.plot_value()
        self.assertEqual(len(self.images), n)
        self.assertEqual(len(self.tkmod.BUILDS), 1)

    def test_every_kind_is_built_once_and_a_change_of_kind_removes_the_last_kinds_items(self):
        ctrl = self.controller(Zctrl())
        ctrl.config(Zctrl(ticks=[0, 1], labels=["Off", "On"], value=1, is_toggle=True))
        ctrl.show()
        self.assertEqual((ctrl.of("image"), ctrl.of("line")), ([], []))
        self.assertEqual(len(ctrl.of("oval")), 3)


class TheThread(TkControllerCase):
    def test_a_value_set_from_another_thread_makes_no_canvas_and_no_image_call_there_and_tks_next_plot_moves_the_pointer(self):
        ctrl = self.controller(Zctrl(value=0.25))
        pointer = self.line_of(ctrl, self.config.color_knob_pointer)[0]
        before, images, builds = pointer["coords"], len(self.images), len(self.tkmod.BUILDS)
        mark = len(ctrl.threads)

        def other():
            ctrl.zctrl.value = 0.75
            ctrl.calculate_plot_values()

        t = threading.Thread(target=other)
        t.start()
        t.join()
        self.assertEqual(ctrl.threads[mark:], [], "a canvas call was made by the thread that set the value")
        self.assertEqual((len(self.images), len(self.tkmod.BUILDS)), (images, builds))
        self.assertEqual(pointer["coords"], before)
        ctrl.plot_value()  # Tk's thread, the plot task
        self.assertNotEqual(pointer["coords"], before)
        self.assertEqual(set(ctrl.threads[mark:]), {threading.get_ident()})

    def test_there_is_no_after_idle_hop_in_the_look(self):
        self.assertNotIn("after_idle", open(TK).read())


@unittest.skipUnless(Image, "no PIL")
class ThePixels(unittest.TestCase):
    """The PIL face itself, read at the points the design names (docs/ui-look-tk-widgets.md, section 5, stage 1)."""

    def setUp(self):
        self.cls, self.config, self.loaded = load_tk_controller(LOOK)
        self.tk = self.loaded["zyngui.zynthian_gui_controller_tk"]
        self.tk.FACES.clear()
        self.size = 168

    def face(self, **override):
        tokens = {k: getattr(self.config, k) for k in self.tk.FACE_TOKENS}
        tokens.update(override)
        return self.tk.knob_face(self.size, tuple(sorted(tokens.items())))

    def at(self, im, r, deg):
        """The pixel at <r> radii from the centre, <deg> clockwise from 12 o'clock."""
        c, R = self.size / 2, self.size / 2
        a = math.radians(deg)
        return im.getpixel((round(c + math.sin(a) * r * R), round(c - math.cos(a) * r * R)))[:3]

    def near(self, a, b, levels=3):
        return all(abs(x - y) <= levels for x, y in zip(a, b))

    def focus(self):
        """The cap's highlight: (0.35, 0.3) of the cap's box, 0.70 of the radius across."""
        R = self.size / 2
        return (round(R + (0.35 - 0.5) * 2 * 0.70 * R), round(R + (0.3 - 0.5) * 2 * 0.70 * R))

    def test_the_cap_at_the_focus_is_the_highlight_token(self):
        im = self.face()
        self.assertTrue(self.near(im.getpixel(self.focus())[:3], rgb(self.config.color_knob_cap_hi)), im.getpixel(self.focus()))

    def test_the_cap_on_the_far_side_is_the_face_token(self):
        im = self.face()
        fx, fy = self.focus()
        R = self.size / 2
        n = math.hypot(R - fx, R - fy)
        far = (round(R + (R - fx) / n * 0.66 * R), round(R + (R - fy) / n * 0.66 * R))  # opposite the focus, inside the cap
        d = math.hypot(far[0] - R, far[1] - R) / R
        self.assertLess(d, 0.70)
        self.assertTrue(self.near(im.getpixel(far)[:3], rgb(self.config.color_knob_face)), (d, im.getpixel(far)))

    def test_the_rim_ring_is_the_edge_token_and_the_knurl_ring_the_knurl_token(self):
        im = self.face()
        for deg in (7.5, 100, 200, 301.5):  # between the knurl lines, which fall every 15 degrees
            self.assertTrue(self.near(self.at(im, 0.77, deg), rgb(self.config.color_knob_edge)), deg)
        self.assertTrue(self.near(self.at(im, 0.715, 7.5), rgb(self.config.color_knob_knurl)))

    def test_a_tick_is_the_highlight_colour_at_minus_135_and_plus_135_degrees(self):
        im = self.face()
        for deg in (-135, 135, 0):
            self.assertTrue(self.near(self.at(im, 0.915, deg), rgb(self.config.color_hl)), deg)
        self.assertTrue(self.near(self.at(im, 0.915, 13.5), rgb(self.config.color_panel_bg)), "between two ticks is the ground")

    def test_another_token_set_moves_each(self):
        im = self.face(color_knob_face="#112233", color_knob_cap_hi="#ddeeff", color_knob_edge="#aa0000",
                       color_knob_knurl="#00aa00", color_hl="#0000ff")
        self.assertTrue(self.near(im.getpixel(self.focus())[:3], rgb("#ddeeff")))
        self.assertTrue(self.near(self.at(im, 0.77, 100), rgb("#aa0000")))
        self.assertTrue(self.near(self.at(im, 0.715, 7.5), rgb("#00aa00")))
        self.assertTrue(self.near(self.at(im, 0.915, 135), rgb("#0000ff")))

    def test_a_face_is_cached_by_its_size_and_tokens(self):
        a, b = self.face(), self.face()
        self.assertIs(a, b)
        self.assertEqual(len(self.tk.BUILDS), 1)
        self.face(color_knob_face="#112233")
        self.assertEqual(len(self.tk.BUILDS), 2)


class TheRemovals(unittest.TestCase):
    def test_the_renderers_controller_module_is_gone_and_the_tail_binds_the_tk_one(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "zyngui", "zynthian_gui_controller_drawn.py")))
        self.assertIn("zynthian_gui_controller_tk", open(CONTROLLER).read())
        self.assertNotIn("controller_drawn", open(CONTROLLER).read())

    def test_the_tk_look_imports_no_renderer_and_no_look_table(self):
        text = open(TK).read()
        for word in ("zynthian_omx_panel_view", "zynthian_ui_look", "libomx-panel-render", "RendererAbsent"):
            self.assertNotIn(word, text)

    def test_the_old_controller_tests_of_the_renderer_path_are_gone(self):
        text = open(os.path.join(ROOT, "tests", "test_ui_look_widgets.py")).read()
        for word in ("class DrawnController", "class RealRenderer", "FakeView(", "def load_controller"):
            self.assertNotIn(word, text)

    def test_ci_installs_what_the_tk_tests_import(self):
        text = open(os.path.join(ROOT, ".github", "workflows", "tests.yml")).read()
        self.assertNotIn("no PIL|no omx-panel tools directory", text)
        self.assertIn("python3-pil", text)


class WhatCIMustHave(unittest.TestCase):
    @unittest.skipUnless(CI, "a desk may lack PIL: the Tk tests skip and say so")
    def test_ci_has_pil_so_the_tk_controller_tests_run(self):
        self.assertIsNotNone(Image, "CI has no PIL (python3-pil): every Tk controller test skipped and ran nothing")


if __name__ == "__main__":
    unittest.main()
