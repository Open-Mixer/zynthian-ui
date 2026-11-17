# -*- coding: utf-8 -*-
#
# The UI look draws the stock controller widget (docs/ui-look-drawn-widgets.md, zynthian-ui#53 level 2).
# ZYNTHIAN_UI_LOOK chooses the drawing: `stock` is upstream Zynthian's widget, the class zyngui/zynthian_gui_controller.py
# defines, its canvas items created and configured as upstream does, the drawn module never imported; `vintage` draws
# every controller through omx-panel's renderer (zyngine/zynthian_omx_panel_view.py), one panel description of one
# control per controller, the renderer's RGBA painted over color_panel_bg as one canvas image, the selection a frame
# in the colour the stock arc would take. The look the view is opened with is the UI's palette over the renderer's own
# look.json (zyngine/zynthian_ui_look.py): the colour roles Zynthian's palette has a colour for carry the config's
# colour, the others the renderer's base; the preset's colours are zynthian-sys config/ui-looks/openmixer-vintage.sh's.
#
# The config's colour roles and ui_look are the real zynthian_gui_config.py's own lines, run under each look's
# environment; the controller and the drawn module are the real files over a Tk canvas that records what it is asked
# to draw; the renderer's view is a stand-in that records the description, the look and the readings and draws a PIL
# frame; PIL is real (the Pi has it; CI installs it).
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import importlib.util
import json
import os
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

try:
    from PIL import Image, ImageDraw
except ImportError:  # the Pi has PIL, CI installs it
    Image = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(ROOT, "zyngui", "zynthian_gui_config.py")
CONTROLLER = os.path.join(ROOT, "zyngui", "zynthian_gui_controller.py")
DRAWN = os.path.join(ROOT, "zyngui", "zynthian_gui_controller_drawn.py")
LOOK = os.path.join(ROOT, "zyngine", "zynthian_ui_look.py")
VIEW = os.path.join(ROOT, "zyngine", "zynthian_omx_panel_view.py")
LOOK_BASE = os.path.join(HERE, "fixtures", "omx_panel", "look.json")  # omx-panel tools/look.json, as the package installs it

# The looks as zynthian-sys declares them (config/ui-looks/*.sh): the ZYNTHIAN_UI_COLOR_* each sets
STOCK = {"ZYNTHIAN_UI_COLOR_BG": "#000000", "ZYNTHIAN_UI_COLOR_TX": "#ffffff", "ZYNTHIAN_UI_COLOR_TX_OFF": "#e0e0e0",
         "ZYNTHIAN_UI_COLOR_ON": "#ff0000", "ZYNTHIAN_UI_COLOR_OFF": "#5a626d", "ZYNTHIAN_UI_COLOR_LOW_ON": "#b00000",
         "ZYNTHIAN_UI_COLOR_HL": "#00c000", "ZYNTHIAN_UI_COLOR_ML": "#f0f000", "ZYNTHIAN_UI_COLOR_PANEL_BG": "#3a424d",
         "ZYNTHIAN_UI_COLOR_PANEL_HL": "#2a323d", "ZYNTHIAN_UI_COLOR_INFO": "#8080ff", "ZYNTHIAN_UI_COLOR_MIDI": "#19b1f7",
         "ZYNTHIAN_UI_COLOR_ALT": "#ff00ff", "ZYNTHIAN_UI_COLOR_ALT2": "#ff9000", "ZYNTHIAN_UI_COLOR_ERROR": "#ff0000",
         "ZYNTHIAN_UI_COLOR_WARN": "#ff9000"}
VINTAGE = {"ZYNTHIAN_UI_COLOR_BG": "#0b0e11", "ZYNTHIAN_UI_COLOR_TX": "#eaf0f4", "ZYNTHIAN_UI_COLOR_TX_OFF": "#8a97a3",
           "ZYNTHIAN_UI_COLOR_ON": "#e8732c", "ZYNTHIAN_UI_COLOR_OFF": "#0d1115", "ZYNTHIAN_UI_COLOR_LOW_ON": "#693d24",
           "ZYNTHIAN_UI_COLOR_HL": "#e9dfc6", "ZYNTHIAN_UI_COLOR_ML": "#f2b03a", "ZYNTHIAN_UI_COLOR_PANEL_BG": "#15191e",
           "ZYNTHIAN_UI_COLOR_PANEL_HL": "#242b33", "ZYNTHIAN_UI_COLOR_INFO": "#8a97a3", "ZYNTHIAN_UI_COLOR_MIDI": "#34d17b",
           "ZYNTHIAN_UI_COLOR_ALT": "#34d17b", "ZYNTHIAN_UI_COLOR_ALT2": "#f2b632", "ZYNTHIAN_UI_COLOR_ERROR": "#ff5a4d",
           "ZYNTHIAN_UI_COLOR_WARN": "#ffbf3d", "ZYNTHIAN_UI_LOOK": "vintage"}
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
        self._w = self._h = 1

    def _item(self, kind, *xy, **kw):
        self.n += 1
        self.items[self.n] = {"kind": kind, "coords": xy, "state": "normal", **kw}
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

    def tag_raise(self, *a): pass
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
        self.nudge_factor = self.nudge_factor_fine = 0.01
        self.__dict__.update(kw)
        self.value_range = self.value_max - self.value_min

    def get_value2index(self): return self.ticks.index(self.value)
    def get_value2label(self): return self.labels[self.get_value2index()] if self.labels else str(self.value)
    def set_value(self, v, *a): self.value = v


class FakeView:
    """The renderer's view as the drawn controller uses it: the description and the look it was opened with, the
    readings it was given, and a PIL frame for every draw."""
    opened = []
    refuse = None
    stop_at_draw = False

    def __init__(self, layout, tools_dir=None, look=None):
        if FakeView.refuse:
            raise FakeView.refuse
        self.layout, self.tools_dir, self.look = layout, tools_dir, look
        self.symbols = [c["symbol"] for c in layout["controls"]]
        self.meters = []
        self.calls, self.draws, self.closed = [], [], False
        FakeView.opened.append(self)

    def set_title(self, brand, name): self.calls.append(("title", brand, name))
    def set_surface(self, w, h, scale=1.0): self.size = (w, h)
    def set_value(self, i, fraction, text): self.calls.append(("value", i, fraction, text))
    def set_choice(self, i, at, count, text): self.calls.append(("choice", i, at, count, text))
    def set_travel(self, *a, **kw): self.calls.append(("travel",) + a)
    def close(self): self.closed = True

    def draw(self, w, h, scale=1.0):
        if FakeView.stop_at_draw:
            raise FakeView.module.RendererStopped("omx-panel's renderer stopped (SIGSEGV); the panel is drawn again when it is opened again")
        self.draws.append((w, h))
        return frame(w, h)


def frame(w, h):
    """A renderer draw: a translucent face and an opaque pointer, alpha over the background."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((2, 2, w - 3, h - 3), fill=(21, 25, 30, 200))
    d.line((w // 2, h // 2, w // 2, 4), fill=(232, 115, 44, 255), width=3)
    return im.tobytes()


def shown(w, h, bg):
    return Image.alpha_composite(Image.new("RGBA", (w, h), bg), Image.frombuffer("RGBA", (w, h), frame(w, h), "raw", "RGBA", 0, 1))


def load_controller(environ, tools_dir=None):
    """zyngui.zynthian_gui_controller as zynthian_gui.py imports it, with zynthian_gui_config carrying <environ>'s look;
    the renderer's View is FakeView. Returns (the class the module exports, the config, sys.modules as loaded)."""
    FakeView.opened, FakeView.refuse, FakeView.stop_at_draw = [], None, False
    values = config_under(environ)
    zyngui = mock.MagicMock()
    zyngui.chain_manager.get_midi_learn_from_zctrl.return_value = None
    config = types.ModuleType("zyngui.zynthian_gui_config")
    config.__dict__.update({k: v for k, v in values.items() if k != "said"}, font_family="sans", font_size=12,
                           layout={"ctrl_orientation": "horizontal"}, ctrl_graph=1, zyngui=zyngui, num_zynpots=0, select_ctrl=3)
    gui = types.ModuleType("zyngui")
    gui.__path__ = [os.path.join(ROOT, "zyngui")]
    gui.zynthian_gui_config = config
    engine = types.ModuleType("zyngine")
    engine.__path__ = [os.path.join(ROOT, "zyngine")]
    law = types.ModuleType("zyngine.zynthian_position_law")
    law.scale_position = lambda law, value: 0.5
    zyncoder = types.ModuleType("zyncoder")
    zyncore = types.ModuleType("zyncoder.zyncore")
    zyncore.lib_zyncore = mock.MagicMock()
    tk = types.ModuleType("tkinter")
    tk.Canvas, tk.ARC, tk.CENTER, tk.LEFT, tk.S, tk.NW, tk.NORMAL, tk.HIDDEN, tk.FLAT = Canvas, "arc", "center", "left", "s", "nw", "normal", "hidden", "flat"
    tkfont = types.ModuleType("tkinter.font")
    tkfont.Font = Font
    tk.font = tkfont
    view = load_module("zyngine.zynthian_omx_panel_view", VIEW)
    view.View = FakeView
    FakeView.module = view
    if tools_dir:
        view.TOOLS_DIR = tools_dir
    modules = {"tkinter": tk, "tkinter.font": tkfont, "zyngui": gui, "zyngui.zynthian_gui_config": config, "zyngine": engine,
               "zyngine.zynthian_position_law": law, "zyngine.zynthian_omx_panel_view": view, "zyncoder": zyncoder,
               "zyncoder.zyncore": zyncore}
    for name in [m for m in sys.modules if m.startswith("zyngui.zynthian_gui_controller_drawn") or m == "zyngine.zynthian_ui_look"]:
        modules[name] = None
    with mock.patch.dict(sys.modules, modules):
        for name in [m for m, v in modules.items() if v is None]:
            del sys.modules[name]
        module = load_module("zynthian_gui_controller_under_test", CONTROLLER)
        loaded = dict(sys.modules)
    return module.zynthian_gui_controller, config, loaded


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


# ---- Stock is upstream

class StockIsUpstream(unittest.TestCase):
    def test_the_exported_class_is_the_files_own_and_the_drawn_module_is_not_imported(self):
        cls, _, loaded = load_controller(STOCK)
        self.assertEqual(cls.__name__, "zynthian_gui_controller")
        self.assertEqual(cls.__module__, "zynthian_gui_controller_under_test")
        self.assertNotIn("zyngui.zynthian_gui_controller_drawn", loaded)
        self.assertNotIn("zyngine.zynthian_ui_look", loaded)

    def test_stock_draws_the_upstream_items_and_no_image(self):
        cls, config, _ = load_controller(STOCK)
        ctrl = cls(0, None, Zctrl())
        ctrl._w, ctrl._h = 120, 100
        ctrl.on_size(None)
        ctrl.set_hl()
        self.assertEqual([o["kind"] for o in ctrl.items.values()], ["arc", "arc", "text", "text", "text"])
        self.assertEqual(ctrl.items[ctrl.graph]["outline"], config.color_hl)
        self.assertEqual(ctrl.items[ctrl.graph]["state"], "normal")
        self.assertEqual(ctrl.of("image"), [])
        self.assertEqual(FakeView.opened, [])

    def test_the_stock_file_knows_no_look_renderer_or_pil_but_its_tail(self):
        tree = ast.parse(open(CONTROLLER).read())
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "zynthian_gui_controller")
        words = re.compile(r"ui_look|drawn|renderer|panel_view|PIL", re.I)
        for node in ast.walk(klass):
            for text in ([node.id] if isinstance(node, ast.Name) else [node.attr] if isinstance(node, ast.Attribute)
                         else [node.value] if isinstance(node, ast.Constant) and isinstance(node.value, str) else []):
                self.assertFalse(words.search(text), f"line {node.lineno}: {text!r} in the stock class")
        tails = [n for n in tree.body if isinstance(n, ast.If)]
        self.assertEqual(len(tails), 1, "one module-level if: the look's class takes the name when the look is not stock")
        self.assertIn("ui_look", ast.dump(tails[0].test))
        self.assertEqual(tails[0].orelse, [], "stock has no branch: nothing runs for it")


# ---- The drawn controller

@unittest.skipUnless(Image, "no PIL")
class DrawnController(unittest.TestCase):
    def setUp(self):
        self.tools = tools_dir_with(json.load(open(LOOK_BASE)))
        self.cls, self.config, _ = load_controller(VINTAGE, tools_dir=self.tools)
        self.images = []
        test = self

        class Recorded(self.cls):
            def photo_of(self, image):
                test.images.append(image)
                return ("photo", image.size)

        self.Recorded = Recorded

    def controller(self, zctrl, w=120, h=100, **kw):
        ctrl = self.Recorded(0, None, zctrl, **kw)
        ctrl._w, ctrl._h = w, h
        ctrl.on_size(None)
        return ctrl

    def test_it_is_a_subclass_of_the_stock_widget_overriding_only_what_paints(self):
        self.assertEqual(self.cls.__name__, "zynthian_gui_controller_drawn")
        stock = self.cls.__mro__[1]
        self.assertEqual(stock.__name__, "zynthian_gui_controller")
        own = {k for k, v in vars(self.cls).items() if callable(v) and not k.startswith("__")}
        overridden = own & set(vars(stock))
        self.assertEqual(overridden, {"show", "on_size", "plot_value", "set_title", "_set_color_graph"})

    def test_a_numeric_controller_is_a_knob_with_its_value(self):
        ctrl = self.controller(Zctrl(value=0.25))
        view = FakeView.opened[-1]
        self.assertEqual(view.layout["controls"], [{"symbol": "cutoff", "label": "Cutoff", "section": 0, "standard": {"widget": "knob"}}])
        self.assertEqual(len(view.layout["sections"]), 1)
        self.assertEqual(view.size, (120, 100))
        self.assertEqual(view.calls[-1], ("value", 0, 0.25, ctrl.value_print))
        self.assertEqual(ctrl.value_print, "0.25")

    def test_a_list_of_values_is_a_selector_with_the_chosen_one(self):
        z = Zctrl(ticks=[0, 1, 2, 3], labels=["Sine", "Saw", "Square", "Noise"], value=2)
        self.controller(z)
        view = FakeView.opened[-1]
        self.assertEqual(view.layout["controls"][0]["standard"], {"widget": "selector"})
        self.assertEqual(view.calls[-1], ("choice", 0, 2, 4, "Square"))

    def test_a_two_value_list_is_a_switch(self):
        self.controller(Zctrl(ticks=[0, 1], labels=["Off", "On"], value=1, is_toggle=True))
        view = FakeView.opened[-1]
        self.assertEqual(view.layout["controls"][0]["standard"], {"widget": "switch"})
        self.assertEqual(view.calls[-1], ("value", 0, 1, "On"))

    def test_a_path_is_a_display_with_its_name(self):
        self.controller(Zctrl(is_path=True, value="/zynthian/media/take 3.wav"))
        view = FakeView.opened[-1]
        self.assertEqual(view.layout["controls"][0]["standard"], {"widget": "display"})
        self.assertEqual(view.calls[-1], ("value", 0, 0, "take 3.wav"))

    def test_the_image_is_the_renderers_frame_over_the_panel_colour_and_the_stock_items_are_hidden(self):
        ctrl = self.controller(Zctrl())
        self.assertEqual(self.images[-1].tobytes(), shown(120, 100, self.config.color_panel_bg).tobytes())
        self.assertEqual(ctrl.items[ctrl.graph]["state"], "hidden")
        self.assertEqual(ctrl.items[ctrl.label_title]["state"], "hidden")
        self.assertEqual(ctrl.items[ctrl.value_text]["state"], "hidden")
        self.assertEqual(len(ctrl.of("image")), 1)

    def test_a_new_value_is_given_to_the_view_and_drawn_once(self):
        ctrl = self.controller(Zctrl(value=0.25))
        view, drawn = FakeView.opened[-1], len(FakeView.opened[-1].draws)
        ctrl.zctrl.value = 0.75
        ctrl.calculate_plot_values()
        ctrl.plot_value()
        self.assertEqual(view.calls[-1], ("value", 0, 0.75, "0.75"))
        self.assertEqual(len(view.draws), drawn + 1)
        ctrl.plot_value()  # nothing moved: nothing drawn
        self.assertEqual(len(view.draws), drawn + 1)

    def test_the_selection_is_a_frame_in_the_highlight_colour_and_none_when_unselected(self):
        ctrl = self.controller(Zctrl())
        ctrl.set_hl()
        frames = [o for o in ctrl.of("rectangle") if o.get("outline") and o["state"] == "normal"]
        self.assertEqual([f["outline"] for f in frames], [self.config.color_hl])
        ctrl.unset_hl()
        self.assertEqual([o for o in ctrl.of("rectangle") if o.get("outline") and o["state"] == "normal"], [])
        ctrl.set_color_readonly()
        frames = [o for o in ctrl.of("rectangle") if o.get("outline") and o["state"] == "normal"]
        self.assertEqual([f["outline"] for f in frames], [self.config.color_ctrl_bg_off])

    def test_the_view_is_opened_with_the_presets_colours_at_their_roles_over_the_renderers_base(self):
        self.controller(Zctrl())
        look = FakeView.opened[-1].look
        base = json.load(open(LOOK_BASE))
        self.assertEqual(set(look["tokens"]), set(base["tokens"]), "every role of the renderer's look, no more")
        for role, colour in VINTAGE_ROLES.items():
            self.assertEqual(look["tokens"][role], colour, role)
        for role in ("--surface-2", "--border", "--ink-faint", "--state-bypass", "--origin-fbs", "--font-file"):
            self.assertEqual(look["tokens"][role], base["tokens"][role], role)

    def test_a_hidden_controller_draws_nothing(self):
        ctrl = self.Recorded(0, None, Zctrl(), hidden=True)
        self.assertEqual(FakeView.opened, [])
        self.assertEqual(self.images, [])

    def test_without_the_renderer_the_stock_widget_is_drawn_and_the_reason_said_once(self):
        FakeView.refuse = FakeView.module.RendererAbsent("omx-panel's renderer (libomx-panel-render.so.0) is not installed: no")
        with self.assertLogs(level="WARNING") as log:
            a = self.controller(Zctrl())
            b = self.controller(Zctrl(symbol="res", short_name="Res"))
        self.assertEqual(len([m for m in log.output if "not installed" in m]), 1, log.output)
        for ctrl in (a, b):
            self.assertEqual(ctrl.items[ctrl.graph]["state"], "normal")
            self.assertEqual(ctrl.of("image"), [])
        self.assertEqual(self.images, [])

    def test_a_renderer_that_stops_after_a_draw_gives_the_stock_items_back(self):
        ctrl = self.controller(Zctrl(value=0.25))
        self.assertEqual(ctrl.items[ctrl.graph]["state"], "hidden")
        FakeView.stop_at_draw = True
        ctrl.zctrl.value = 0.75
        ctrl.calculate_plot_values()
        with self.assertLogs(level="WARNING") as log:
            ctrl.plot_value()
        self.assertEqual(len([m for m in log.output if "stopped" in m]), 1, log.output)
        self.assertEqual(ctrl.items[ctrl.graph]["state"], "normal")
        self.assertEqual(ctrl.items[ctrl.value_text]["state"], "normal")
        self.assertEqual(ctrl.of("image"), [])
        self.assertEqual([o for o in ctrl.of("rectangle") if o["state"] == "normal"], [])
        self.assertTrue(FakeView.opened[-1].closed)


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
        self.assertIsInstance(look, ast.Call)
        self.assertEqual(ast.unparse(look.func), "ui_look.look_for")
        self.assertEqual([ast.unparse(a) for a in look.args], ["zynthian_gui_config", "panel_view.tools_dir()"])


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
