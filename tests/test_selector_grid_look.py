# -*- coding: utf-8 -*-
#
# The main menu's grid (zyngui/zynthian_gui_selector_grid.py, the main menu and the add-chain screen) draws in the
# active UI look (zynthian-ui#55): its ground, tiles, text and selection frame are look tokens of their own
# (ZYNTHIAN_UI_COLOR_GRID_*, zynthian_gui_config's color_grid_*), never a colour of the grid's. Stock is Zynthian's own
# look as upstream draws it: with no token set, or with the stock look's, the grid draws exactly what it drew before
# the tokens, the greys, the white and #aaaaaa text and the yellow frame on the panel colour. A look that sets the
# tokens (OpenMixer vintage) draws in them. The colour roles are the real config's own lines (zynthian_gui_config.py's
# color_* assignments, run under each look's environment; the module itself reads the Pi's wiring at import), the
# grid's drawing methods run over a canvas that records what it is asked to draw; tkinter, PIL and the base screen
# are stand-ins.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import os
import re
import sys
import types
import unittest
import importlib.util
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GRID = os.path.join(ROOT, "zyngui", "zynthian_gui_selector_grid.py")

CONFIG = os.path.join(ROOT, "zyngui", "zynthian_gui_config.py")

# What the grid drew before the tokens, in every look: upstream Zynthian's main menu
UPSTREAM = {"canvas": "#3a424d", "tile": "#666666", "tile_off": "#444444", "text": "#ffffff", "text_off": "#aaaaaa",
            "frame": "yellow", "frame_off": ""}

# The looks as zynthian-sys declares them (config/ui-looks/*.sh): the ZYNTHIAN_UI_COLOR_* each sets
STOCK = {"ZYNTHIAN_UI_COLOR_BG": "#000000", "ZYNTHIAN_UI_COLOR_TX": "#ffffff", "ZYNTHIAN_UI_COLOR_TX_OFF": "#e0e0e0",
         "ZYNTHIAN_UI_COLOR_ON": "#ff0000", "ZYNTHIAN_UI_COLOR_OFF": "#5a626d", "ZYNTHIAN_UI_COLOR_HL": "#00c000",
         "ZYNTHIAN_UI_COLOR_ML": "#f0f000", "ZYNTHIAN_UI_COLOR_PANEL_BG": "#3a424d",
         "ZYNTHIAN_UI_COLOR_PANEL_HL": "#2a323d",
         "ZYNTHIAN_UI_COLOR_GRID_BG": "#3a424d", "ZYNTHIAN_UI_COLOR_GRID_TILE": "#666666",
         "ZYNTHIAN_UI_COLOR_GRID_TILE_OFF": "#444444", "ZYNTHIAN_UI_COLOR_GRID_TX": "#ffffff",
         "ZYNTHIAN_UI_COLOR_GRID_TX_OFF": "#aaaaaa", "ZYNTHIAN_UI_COLOR_GRID_SEL": "yellow"}
VINTAGE = {"ZYNTHIAN_UI_COLOR_BG": "#0b0e11", "ZYNTHIAN_UI_COLOR_TX": "#eaf0f4", "ZYNTHIAN_UI_COLOR_TX_OFF": "#8a97a3",
           "ZYNTHIAN_UI_COLOR_ON": "#e8732c", "ZYNTHIAN_UI_COLOR_OFF": "#0d1115", "ZYNTHIAN_UI_COLOR_HL": "#e9dfc6",
           "ZYNTHIAN_UI_COLOR_ML": "#f2b03a", "ZYNTHIAN_UI_COLOR_PANEL_BG": "#15191e",
           "ZYNTHIAN_UI_COLOR_PANEL_HL": "#242b33",
           "ZYNTHIAN_UI_COLOR_GRID_BG": "#0b0e11", "ZYNTHIAN_UI_COLOR_GRID_TILE": "#15191e",
           "ZYNTHIAN_UI_COLOR_GRID_TILE_OFF": "#242b33", "ZYNTHIAN_UI_COLOR_GRID_TX": "#eaf0f4",
           "ZYNTHIAN_UI_COLOR_GRID_TX_OFF": "#8a97a3", "ZYNTHIAN_UI_COLOR_GRID_SEL": "#e8732c"}
GRID_TOKENS = {"canvas": "ZYNTHIAN_UI_COLOR_GRID_BG", "tile": "ZYNTHIAN_UI_COLOR_GRID_TILE",
               "tile_off": "ZYNTHIAN_UI_COLOR_GRID_TILE_OFF", "text": "ZYNTHIAN_UI_COLOR_GRID_TX",
               "text_off": "ZYNTHIAN_UI_COLOR_GRID_TX_OFF", "frame": "ZYNTHIAN_UI_COLOR_GRID_SEL"}


def roles(environ):
    """zynthian_gui_config's colour roles under <environ>: its own module-level color_* lines, run in order."""
    tree = ast.parse(open(CONFIG).read())
    lines = [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
             and isinstance(n.targets[0], ast.Name) and n.targets[0].id.startswith("color_")]
    space = {"os": types.SimpleNamespace(environ=dict(environ))}
    exec(compile(ast.Module(body=lines, type_ignores=[]), CONFIG, "exec"), space)
    return {k: v for k, v in space.items() if k.startswith("color_")}


class Canvas:
    """Records each item's options, by its tags, as Tk's canvas would hold them."""

    def __init__(self):
        self.items = []

    def _add(self, kind, kw):
        self.items.append((kind, set(kw.get("tags", ())), dict(kw)))

    def create_rectangle(self, *xy, **kw):
        self._add("rect", kw)

    def create_text(self, *xy, **kw):
        self._add("text", kw)

    def create_image(self, *xy, **kw):
        self._add("image", kw)

    def itemconfig(self, tags, **kw):
        want = {t.strip() for t in tags.split("&&")}
        for _, have, opts in self.items:
            if want <= have:
                opts.update(kw)

    def bbox(self, *a):
        return None

    def opts(self, kind, idx):
        return next(o for k, t, o in self.items if k == kind and f"node_{idx}" in t)


def load_grid(look):
    """zynthian_gui_selector_grid as zynthian_gui.py loads it, with zynthian_gui_config carrying <look>."""
    config = types.ModuleType("zyngui.zynthian_gui_config")
    config.__dict__.update(roles(look), font_family="sans")
    gui = types.ModuleType("zyngui")
    gui.__path__ = []
    gui.zynthian_gui_config = config
    base = types.ModuleType("zyngui.zynthian_gui_base")
    base.zynthian_gui_base = type("zynthian_gui_base", (), {"__init__": lambda self: setattr(self, "main_frame", None)})
    pil = types.ModuleType("PIL")
    pil.Image = pil.ImageTk = mock.MagicMock()
    tk = mock.MagicMock(CENTER="center", BOTH="both")
    modules = {"tkinter": tk, "PIL": pil, "zyngui": gui, "zyngui.zynthian_gui_config": config,
               "zyngui.zynthian_gui_base": base}
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("zynthian_gui_selector_grid_under_test", GRID)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module.zynthian_gui_selector_grid, tk


def drawn(look):
    """What the grid draws under <look>: its canvas, an action tile (0), a tile with no action (1), tile 0 selected."""
    cls, tk = load_grid(look)
    grid = cls()
    background = tk.Canvas.call_args.kwargs["bg"]
    grid.canvas = Canvas()
    grid.BLOCK_WIDTH, grid.BLOCK_HEIGHT, grid.font = 120, 40, ("sans", 8)
    grid.config = [{"title": "Mixer", "action": lambda: None}, {"title": "Admin", "action": None}]
    grid.selected_node, grid.shown, grid.width, grid.height = 0, False, 400, 300
    for idx, node in enumerate(grid.config):
        grid._draw_node(idx, node, 10 + 130 * idx, 10)
    grid._draw_selection()
    c = grid.canvas
    return {"canvas": background, "tile": c.opts("rect", 0)["fill"], "tile_off": c.opts("rect", 1)["fill"],
            "text": c.opts("text", 0)["fill"], "text_off": c.opts("text", 1)["fill"],
            "frame": c.opts("rect", 0)["outline"], "frame_off": c.opts("rect", 1)["outline"]}


# A Tk option that names a colour, and a literal that is one
COLOUR_OPTIONS = {"fill", "outline", "bg", "fg", "background", "foreground", "activefill", "activeoutline",
                  "disabledfill", "selectbackground", "selectforeground", "highlightcolor", "highlightbackground"}
HEX = re.compile(r"^#[0-9a-fA-F]{3,12}$")


class SelectorGridLook(unittest.TestCase):
    def test_no_colour_of_its_own(self):
        """No #rrggbb anywhere in the grid, and no literal (a colour name) given to a colour option but '' (none)."""
        found = []
        for node in ast.walk(ast.parse(open(GRID).read())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and HEX.match(node.value):
                found.append(f"line {node.lineno}: {node.value!r}")
            if isinstance(node, ast.keyword) and node.arg in COLOUR_OPTIONS:
                for value in ast.walk(node.value):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value != "":
                        found.append(f"line {value.lineno}: {node.arg}={value.value!r}")
        self.assertEqual(sorted(set(found)), [], "a colour the active look does not set")

    def test_stock_is_upstream(self):
        """With no look set, and with the stock look, the grid draws exactly what upstream Zynthian draws."""
        for name, look in (("no look", {}), ("stock", STOCK)):
            with self.subTest(look=name):
                self.assertEqual(drawn(look), UPSTREAM)

    def test_a_look_draws_its_tokens(self):
        """Vintage's grid is its own tokens, part by part; no tile is the colour of its ground."""
        d = drawn(VINTAGE)
        self.assertEqual(d, dict({part: VINTAGE[key] for part, key in GRID_TOKENS.items()}, frame_off=""))
        self.assertNotIn(d["canvas"], (d["tile"], d["tile_off"]))

    def test_each_token_moves_its_part_alone(self):
        """Each token, set on its own over stock, changes its part of the grid and no other."""
        for part, key in GRID_TOKENS.items():
            with self.subTest(token=key):
                d = drawn(dict(STOCK, **{key: "#123456"}))
                self.assertEqual(d, dict(UPSTREAM, **{part: "#123456"}))


if __name__ == "__main__":
    unittest.main()
