# -*- coding: utf-8 -*-
#
# The UI look's switch and the renderer's look table (docs/ui-look-drawn-widgets.md, zynthian-ui#53): ZYNTHIAN_UI_LOOK
# chooses the drawing, and the plugin panel is still drawn through omx-panel's renderer in the UI's palette over the
# renderer's own look.json (zyngine/zynthian_ui_look.py) until its stage 2 (zynthian-ui#93). The controller's drawing is
# Tk and PIL now: tests/test_tk_controller.py holds it. Here the config's colour roles and ui_look are the real
# zynthian_gui_config.py's own lines, run under each look's environment; the helpers (Canvas, Font, Zctrl) are shared.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import importlib.util
import json
import os
import re
import sys
import shutil
import tempfile
import types
import unittest
from unittest import mock

from tests.omx_panel_widget_stub import load_widget

try:
    from PIL import Image, ImageDraw
except ImportError:  # the Pi has PIL, CI installs it
    Image = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(ROOT, "zyngui", "zynthian_gui_config.py")
CONTROLLER = os.path.join(ROOT, "zyngui", "zynthian_gui_controller.py")
LOOK = os.path.join(ROOT, "zyngine", "zynthian_ui_look.py")
VIEW = os.path.join(ROOT, "zyngine", "zynthian_omx_panel_view.py")
LOOK_BASE = os.path.join(HERE, "fixtures", "omx_panel", "look.json")  # omx-panel tools/look.json, as the package installs it
CI = os.environ.get("CI") == "true"  # where a skip is a test that ran nothing: refused

# The looks as zynthian-sys declares them (config/ui-looks/*.sh): the ZYNTHIAN_UI_COLOR_* each sets
STOCK = {"ZYNTHIAN_UI_COLOR_BG": "#000000", "ZYNTHIAN_UI_COLOR_TX": "#ffffff", "ZYNTHIAN_UI_COLOR_TX_OFF": "#e0e0e0",
         "ZYNTHIAN_UI_COLOR_ON": "#ff0000", "ZYNTHIAN_UI_COLOR_OFF": "#5a626d", "ZYNTHIAN_UI_COLOR_LOW_ON": "#b00000",
         "ZYNTHIAN_UI_COLOR_HL": "#00c000", "ZYNTHIAN_UI_COLOR_ML": "#f0f000", "ZYNTHIAN_UI_COLOR_PANEL_BG": "#3a424d",
         "ZYNTHIAN_UI_COLOR_PANEL_HL": "#2a323d", "ZYNTHIAN_UI_COLOR_INFO": "#8080ff", "ZYNTHIAN_UI_COLOR_MIDI": "#19b1f7",
         "ZYNTHIAN_UI_COLOR_ALT": "#ff00ff", "ZYNTHIAN_UI_COLOR_ALT2": "#ff9000", "ZYNTHIAN_UI_COLOR_ERROR": "#ff0000",
         "ZYNTHIAN_UI_COLOR_WARN": "#ff9000"}
# the knob's metal as the vintage preset carries it (zynthian-sys config/ui-looks/openmixer-vintage.sh)
KNOB = {"ZYNTHIAN_UI_COLOR_KNOB_FACE": "#7d848b", "ZYNTHIAN_UI_COLOR_KNOB_EDGE": "#a9b0b7",
        "ZYNTHIAN_UI_COLOR_KNOB_CAP_HI": "#b9c0c6", "ZYNTHIAN_UI_COLOR_KNOB_KNURL": "#5d646b",
        "ZYNTHIAN_UI_COLOR_KNOB_POINTER": "#f4efe2", "ZYNTHIAN_UI_COLOR_SWITCH_TRACK": "#3b4046",
        "ZYNTHIAN_UI_COLOR_SWITCH_THUMB": "#a9b0b7"}
VINTAGE = {"ZYNTHIAN_UI_COLOR_BG": "#0b0e11", "ZYNTHIAN_UI_COLOR_TX": "#eaf0f4", "ZYNTHIAN_UI_COLOR_TX_OFF": "#8a97a3",
           "ZYNTHIAN_UI_COLOR_ON": "#e8732c", "ZYNTHIAN_UI_COLOR_OFF": "#0d1115", "ZYNTHIAN_UI_COLOR_LOW_ON": "#693d24",
           "ZYNTHIAN_UI_COLOR_HL": "#e9dfc6", "ZYNTHIAN_UI_COLOR_ML": "#f2b03a", "ZYNTHIAN_UI_COLOR_PANEL_BG": "#15191e",
           "ZYNTHIAN_UI_COLOR_PANEL_HL": "#242b33", "ZYNTHIAN_UI_COLOR_INFO": "#8a97a3", "ZYNTHIAN_UI_COLOR_MIDI": "#34d17b",
           "ZYNTHIAN_UI_COLOR_ALT": "#34d17b", "ZYNTHIAN_UI_COLOR_ALT2": "#f2b632", "ZYNTHIAN_UI_COLOR_ERROR": "#ff5a4d",
           "ZYNTHIAN_UI_COLOR_WARN": "#ffbf3d", "ZYNTHIAN_UI_LOOK": "vintage", **KNOB}
# The roles the preset's colours land on, and the console token each carries (docs/ui-look-drawn-widgets.md)
VINTAGE_ROLES = {"--surface": "#15191e", "--surface-3": "#242b33", "--glass": "#0d1115", "--ink": "#eaf0f4",
                 "--ink-dim": "#8a97a3", "--legend": "#e9dfc6", "--accent": "#e8732c", "--state-engaged": "#f2b03a",
                 "--meter-green": "#34d17b", "--meter-amber": "#f2b632", "--meter-red": "#ff5a4d"}


def config_under(environ):
    """zynthian_gui_config's colour roles and ui_look under <environ>: its own module-level lines, run in order."""
    tree = ast.parse(open(CONFIG).read())
    names = lambda n: {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}
    lines = [n for n in tree.body if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                                      and (n.targets[0].id.startswith("color_") or n.targets[0].id == "ui_look"))
             or (isinstance(n, ast.If) and "ui_look" in names(n.test))]
    said = []
    log = types.SimpleNamespace(warning=lambda msg, *a: said.append(msg % a if a else msg), error=lambda *a: said.append(a))
    space = {"os": types.SimpleNamespace(environ=dict(environ)), "logging": log}
    exec(compile(ast.Module(body=lines, type_ignores=[]), CONFIG, "exec"), space)
    values = {k: v for k, v in space.items() if k.startswith("color_") or k == "ui_look"}
    values["said"] = said
    return values


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- Tk, as the controller sees it: a canvas that records its items

class Canvas:
    """A Tk canvas as a dict of items, each its options; tags, state and coords as the widget sets them."""

    def __init__(self, parent=None, **kw):
        self.kw, self.items, self.n = kw, {}, 0
        self.order = []  # the stacking order, bottom first
        self._w = self._h = 1

    def _item(self, kind, *xy, **kw):
        self.n += 1
        self.items[self.n] = {"kind": kind, "coords": xy, "state": "normal", **kw}
        self.order.append(self.n)
        return self.n

    def create_arc(self, *xy, **kw): return self._item("arc", *xy, **kw)
    def create_text(self, *xy, **kw): return self._item("text", *xy, **kw)
    def create_rectangle(self, *xy, **kw): return self._item("rectangle", *xy, **kw)
    def create_polygon(self, *xy, **kw): return self._item("polygon", *xy, **kw)
    def create_image(self, *xy, **kw): return self._item("image", *xy, **kw)

    def _ids(self, item):
        if isinstance(item, str):
            return [i for i, o in self.items.items() if item in (o.get("tags") or ())]
        return [item]

    def itemconfig(self, item, **kw):
        for i in self._ids(item):
            self.items[i].update(kw)

    itemconfigure = itemconfig

    def coords(self, item, *xy):
        self.items[item]["coords"] = xy

    def delete(self, item):
        for i in self._ids(item):
            self.items.pop(i, None)
            self.order.remove(i)

    def tag_raise(self, item, above=None):
        for i in self._ids(item):
            self.order.remove(i)
            self.order.append(i)
    def bind(self, *a, **kw): pass
    def winfo_width(self): return self._w
    def winfo_height(self): return self._h
    def bbox(self, item): return (0, 0, 10, 10)

    def of(self, kind):
        return [o for o in self.items.values() if o["kind"] == kind]


class Font:
    def __init__(self, family=None, size=12, **kw): self.size = size
    def copy(self): return Font(size=self.size)
    def measure(self, text): return 6 * len(text)
    def config(self, size=None, **kw):
        if size is not None:
            self.size = size
    configure = config


class Zctrl:
    def __init__(self, **kw):
        self.symbol, self.short_name, self.name = "cutoff", "Cutoff", "Cutoff"
        self.value, self.value_min, self.value_max, self.value_default = 0.25, 0.0, 1.0, 0.5
        self.ticks = self.labels = None
        self.is_logarithmic = self.is_path = self.is_integer = self.is_toggle = self.readonly = False
        self.position_law = None
        self.toggle_declared = None  # the engine's own word on toggles (zynthian_controller): None where it said none
        self.nudge_factor = self.nudge_factor_fine = 0.01
        self.__dict__.update(kw)
        self.value_range = self.value_max - self.value_min

    def get_value2index(self): return self.ticks.index(self.value)
    def get_value2label(self): return self.labels[self.get_value2index()] if self.labels else str(self.value)
    def set_value(self, v, *a): self.value = v


def tools_dir_with(base):
    """A tools directory as omx-panel installs it, with <base> as its look.json."""
    d = tempfile.mkdtemp(suffix=".tools")
    with open(os.path.join(d, "look.json"), "w") as f:
        json.dump(base, f)
    os.mkdir(os.path.join(d, "look"))
    with open(os.path.join(d, "look", "geometry.json"), "w") as f:
        f.write("{}")
    os.mkdir(os.path.join(d, "fonts"))
    with open(os.path.join(d, "fonts", "Inter-Regular.ttf"), "wb") as f:
        f.write(b"\0")
    with open(os.path.join(d, "gestures.json"), "w") as f:
        f.write("{}")
    return d


# ---- The switch

class LookSwitch(unittest.TestCase):
    def test_unset_is_stock(self):
        self.assertEqual(config_under(STOCK)["ui_look"], "stock")

    def test_stock_and_vintage_are_the_looks(self):
        self.assertEqual(config_under({**STOCK, "ZYNTHIAN_UI_LOOK": "stock"})["ui_look"], "stock")
        self.assertEqual(config_under(VINTAGE)["ui_look"], "vintage")

    def test_a_word_that_is_no_look_is_refused_by_name_and_draws_stock(self):
        values = config_under({**STOCK, "ZYNTHIAN_UI_LOOK": "chrome"})
        self.assertEqual(values["ui_look"], "stock")
        self.assertTrue(any("chrome" in str(s) for s in values["said"]), values["said"])


# ---- The look's fixture

class WhatCIMustHave(unittest.TestCase):
    @unittest.skipUnless(CI, "a desk may lack omx-panel's tools: the drift check skips and says so")
    def test_ci_names_omx_panels_tools_so_the_fixture_is_held(self):
        self.assertTrue(os.environ.get("ZYNTHIAN_OMX_PANEL_TOOLS"), "CI names no $ZYNTHIAN_OMX_PANEL_TOOLS: the fixture drift check ran nothing")



# ---- The plugin panel over a look short of a role

class PanelOverAShortLook(unittest.TestCase):
    def test_a_look_short_of_a_role_draws_strips_and_is_said_once(self):
        base = json.load(open(LOOK_BASE))
        tools = tools_dir_with({**base, "tokens": {k: v for k, v in base["tokens"].items() if k != "--legend"}})
        module, panel_view, modules = load_widget(ui_look="vintage", color_panel_bg="#15191e", color_panel_hl="#242b33",
                                                 color_off="#0d1115", color_hl="#e9dfc6", color_ml="#f2b03a", color_midi="#34d17b",
                                                 color_alt2="#f2b632", color_error="#ff5a4d")
        opened = []
        with mock.patch.dict(sys.modules, modules), mock.patch.dict(os.environ, {"ZYNTHIAN_OMX_PANEL_TOOLS": tools}), \
                mock.patch.object(panel_view, "View", lambda *a, **kw: opened.append(kw) or mock.MagicMock(symbols=[], meters=[])), \
                mock.patch.object(panel_view, "screen_part", lambda layout, keys: (layout, {})):
            module.zynthian_widget_omx_panel.said = False
            w = module.zynthian_widget_omx_panel(None)
            w.width, w.height = 120, 60
            w.zyngui_control = types.SimpleNamespace(zcontrollers=[], show_menu=lambda: None)
            engine = types.SimpleNamespace(drawn=({"controls": []},), name="omx eq8", zctrls={}, curve=lambda d: [], meter=lambda s: None)
            with self.assertLogs(level="WARNING") as log:
                w.set_processor(types.SimpleNamespace(engine=engine))  # builds: the first refusal
                self.assertFalse(w.build_drawn())
                self.assertFalse(w.build_drawn())
        self.assertEqual(len([m for m in log.output if "--legend" in m]), 1, log.output)
        self.assertEqual(opened, [], "no view is opened in the renderer's own look")


# ---- The fixture is omx-panel's file

class LookBaseFixture(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ZYNTHIAN_OMX_PANEL_TOOLS"), "no omx-panel tools directory ($ZYNTHIAN_OMX_PANEL_TOOLS, CI builds one)")
    def test_the_fixture_is_the_renderers_look_json_byte_for_byte(self):
        theirs = os.path.join(os.environ["ZYNTHIAN_OMX_PANEL_TOOLS"], "look.json")
        if not os.path.exists(theirs):
            self.fail(f"$ZYNTHIAN_OMX_PANEL_TOOLS names {os.environ['ZYNTHIAN_OMX_PANEL_TOOLS']}, which holds no look.json")
        with open(LOOK_BASE, "rb") as ours, open(theirs, "rb") as theirs:
            self.assertEqual(ours.read(), theirs.read(), "tests/fixtures/omx_panel/look.json drifted from omx-panel tools/look.json")


# ---- The look table

class LookTable(unittest.TestCase):
    def setUp(self):
        self.look = load_module("zynthian_ui_look_under_test", LOOK)
        self.base = json.load(open(LOOK_BASE))

    def test_the_palettes_roles_carry_the_configs_colours_and_the_others_the_base(self):
        config = types.SimpleNamespace(**{k: v for k, v in config_under(VINTAGE).items() if k.startswith("color_")})
        look = self.look.tokens(config, self.base)
        self.assertEqual(set(look["tokens"]), set(self.base["tokens"]))
        for role, colour in VINTAGE_ROLES.items():
            self.assertEqual(look["tokens"][role], colour, role)
        self.assertEqual(look["tokens"]["--surface-2"], self.base["tokens"]["--surface-2"])
        self.assertEqual({k: v for k, v in look.items() if k != "tokens"}, {k: v for k, v in self.base.items() if k != "tokens"})

    def test_a_base_short_of_a_role_the_table_names_is_refused_by_name(self):
        short = {**self.base, "tokens": {k: v for k, v in self.base["tokens"].items() if k != "--legend"}}
        config = types.SimpleNamespace(**{k: v for k, v in config_under(VINTAGE).items() if k.startswith("color_")})
        with self.assertRaises(self.look.LookShort) as cm:
            self.look.tokens(config, short)
        self.assertIn("--legend", str(cm.exception))

    def test_a_base_without_tokens_is_refused_by_name(self):
        config = types.SimpleNamespace(**{k: v for k, v in config_under(VINTAGE).items() if k.startswith("color_")})
        with self.assertRaises(self.look.LookShort) as cm:
            self.look.tokens(config, {"theme": "dark"})
        self.assertIn("tokens", str(cm.exception))

    def test_look_for_reads_the_base_once_and_a_refusal_is_repeated_by_name(self):
        tools = tools_dir_with(self.base)
        vintage = types.SimpleNamespace(**{k: v for k, v in config_under(VINTAGE).items() if k.startswith("color_") or k == "ui_look"})
        first = self.look.look_for(vintage, tools)
        shutil.rmtree(tools)
        self.assertEqual(self.look.look_for(vintage, tools), first)
        short = tools_dir_with({**self.base, "tokens": {k: v for k, v in self.base["tokens"].items() if k != "--accent"}})
        for _ in range(2):
            with self.assertRaises(self.look.LookShort) as cm:
                self.look.look_for(vintage, short)
            self.assertIn("--accent", str(cm.exception))

    def test_look_for_is_none_under_stock_and_the_table_under_vintage(self):
        tools = tools_dir_with(self.base)
        stock = types.SimpleNamespace(ui_look="stock", **{k: v for k, v in config_under(STOCK).items() if k.startswith("color_")})
        self.assertIsNone(self.look.look_for(stock, tools))
        vintage = types.SimpleNamespace(**{k: v for k, v in config_under(VINTAGE).items() if k.startswith("color_") or k == "ui_look"})
        self.assertEqual(self.look.look_for(vintage, tools)["tokens"]["--accent"], "#e8732c")

    def test_look_for_without_the_renderers_tools_is_none(self):
        vintage = types.SimpleNamespace(**{k: v for k, v in config_under(VINTAGE).items() if k.startswith("color_") or k == "ui_look"})
        self.assertIsNone(self.look.look_for(vintage, os.path.join(tempfile.gettempdir(), "no-such-tools-dir")))


# ---- The plugin panel wears the same look

class PanelWearsTheLook(unittest.TestCase):
    def test_the_panel_widget_opens_its_view_with_the_uis_look(self):
        """zynthian_widget_omx_panel's one View(...) call carries look=look_for(zynthian_gui_config, tools_dir()): the
        same table the drawn controller uses (its harness is tests/test_omx_panel_renderer_crash.py's, not repeated)."""
        tree = ast.parse(open(os.path.join(ROOT, "zyngui", "zynthian_widget_omx_panel.py")).read())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "View"]
        self.assertEqual(len(calls), 1)
        look = next((k.value for k in calls[0].keywords if k.arg == "look"), None)
        self.assertIsNotNone(look, "the panel's view is opened in the renderer's own look, not the UI's")
        build = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "build_drawn")
        assigned = {ast.unparse(a.targets[0]): ast.unparse(a.value) for a in ast.walk(build) if isinstance(a, ast.Assign) and len(a.targets) == 1}
        self.assertEqual(assigned.get(ast.unparse(look)), "ui_look.look_for(zynthian_gui_config, panel_view.tools_dir())")


# ---- The look's way to the renderer

class LookDir(unittest.TestCase):
    def setUp(self):
        self.view = load_module("omx_panel_view_under_test", VIEW)
        self.base = json.load(open(LOOK_BASE))
        self.tools = tools_dir_with(self.base)

    def test_a_look_dir_carries_the_hosts_look_and_the_renderers_geometry_font_and_gestures(self):
        look = {**self.base, "tokens": {**self.base["tokens"], "--accent": "#e8732c"}}
        d = self.view.look_dir(look, self.tools)
        self.assertEqual(json.load(open(os.path.join(d, "look.json"))), look)
        for name in ("look/geometry.json", "fonts/Inter-Regular.ttf", "gestures.json"):
            with open(os.path.join(d, name), "rb") as ours, open(os.path.join(self.tools, name), "rb") as theirs:
                self.assertEqual(ours.read(), theirs.read(), name)

    def test_the_view_passes_the_look_to_the_renderers_process(self):
        calls = []
        host = types.SimpleNamespace(call=lambda op, vid, *args: calls.append((op, args)) or (1, ["cutoff"]), alive=lambda: True)
        with mock.patch.object(self.view, "_host", lambda: host):
            self.view.View({"sections": [], "controls": [{"symbol": "cutoff"}]}, None, {"tokens": {}})
        self.assertEqual(calls[0], ("open", ({"sections": [], "controls": [{"symbol": "cutoff"}]}, None, {"tokens": {}})))

    def test_without_a_look_the_renderer_reads_its_own_tools_directory(self):
        calls = []
        host = types.SimpleNamespace(call=lambda op, vid, *args: calls.append((op, args)) or (1, []), alive=lambda: True)
        with mock.patch.object(self.view, "_host", lambda: host):
            self.view.View({"sections": [], "controls": []})
        self.assertEqual(calls[0], ("open", ({"sections": [], "controls": []}, None, None)))


if __name__ == "__main__":
    unittest.main()
