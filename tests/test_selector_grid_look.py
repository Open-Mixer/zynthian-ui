# -*- coding: utf-8 -*-
#
# The main menu's grid (zyngui/zynthian_gui_selector_grid.py, the main menu and the add-chain screen) draws in the
# active UI look (zynthian-ui#55): its tiles, their text and the selection frame read zynthian_gui_config's colours,
# the ones the list screens use for the same roles, never a colour of its own. The grid's own drawing methods run
# under two looks over a canvas that records what it is asked to draw; tkinter, PIL, the config and the base screen
# are stand-ins (the real config reads the Pi's wiring at import).
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

# The colour roles a look sets (ZYNTHIAN_UI_COLOR_*), as zynthian_gui_config names them, with every derived role the
# grid could read. Two looks with no value in common: the values are the stock look's and OpenMixer vintage's.
ROLES = ("color_bg", "color_tx", "color_tx_off", "color_on", "color_off", "color_hl", "color_ml", "color_panel_bg",
         "color_panel_hl")
STOCK = dict(zip(ROLES, ("#000000", "#ffffff", "#e0e0e0", "#ff0000", "#5a626d", "#00c000", "#f0f000", "#3a424d",
                         "#2a323d")))
VINTAGE = dict(zip(ROLES, ("#0b0e11", "#eaf0f4", "#8a97a3", "#e8732c", "#0d1115", "#e9dfc6", "#f2b03a", "#15191e",
                           "#242b33")))


def derived(look):
    """The roles zynthian_gui_config derives from the ones a look sets."""
    c = dict(look)
    c.update(color_panel_tx=look["color_tx"], color_ctrl_bg_on=look["color_on"], color_ctrl_bg_off=look["color_off"],
             color_ctrl_tx=look["color_tx"], color_ctrl_tx_off=look["color_tx_off"], color_header_bg=look["color_bg"],
             color_header_tx=look["color_tx"], color_panel_bd=look["color_bg"])
    return c


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
    config.__dict__.update(derived(look), font_family="sans")
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

    def test_each_part_in_its_role(self):
        """Each part reads the role the list screens use for it: the grid's ground the screen's background, a tile
        the panel (a list on the background), one with no action the panel highlight (as a list item with none), the
        text and its dimmed form, the frame the selection colour."""
        for name, look in (("stock", STOCK), ("vintage", VINTAGE)):
            with self.subTest(look=name):
                c = derived(look)
                self.assertEqual(drawn(look), {
                    "canvas": c["color_bg"], "tile": c["color_panel_bg"], "tile_off": c["color_panel_hl"],
                    "text": c["color_panel_tx"], "text_off": c["color_tx_off"],
                    "frame": c["color_ctrl_bg_on"], "frame_off": ""})

    def test_tiles_stand_out(self):
        """A tile, with an action or none, is never the colour of the ground it is drawn on."""
        for name, look in (("stock", STOCK), ("vintage", VINTAGE)):
            with self.subTest(look=name):
                d = drawn(look)
                self.assertNotIn(d["canvas"], (d["tile"], d["tile_off"]))

    def test_two_looks_two_grids(self):
        """The tiles, the text and the frame all change with the look."""
        stock, vintage = drawn(STOCK), drawn(VINTAGE)
        for part in ("canvas", "tile", "tile_off", "text", "text_off", "frame"):
            with self.subTest(part=part):
                self.assertNotEqual(stock[part], vintage[part])


if __name__ == "__main__":
    unittest.main()
