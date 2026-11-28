# -*- coding: utf-8 -*-
#
# A control page with a blank slot, through the control screen to the panel (zynthian-ui#76): plugin-hostd's pages keep
# a slot omx-panel leaves empty as None (zynthian-ui#52), and the control screen hands the page's four slots to the
# panel widget, which reads every one of them: for the renderer's part of the panel (page_keys), for the strips it
# draws without the renderer (zynthian_panel_gestures.Panel), and on every refresh. A blank slot is drawn empty: the
# renderer's part holds the page's controls and no other, a strip stays in its own slot's row, and the screen opens
# the next page.
#
# The control screen (set_controller_screen, show_widget, plot_zctrls), the panel widget, the gestures and the
# processor are the real files; tkinter, the widget's base, the touch layer and the renderer's view are stand-ins.
#
# Copyright (C) 2026 Pau Aliagas
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

from tests.test_control_short_pages import PAGES, ROOT, load_control, processor, stand_in

WIDGET = os.path.join(ROOT, "zyngui", "zynthian_widget_omx_panel.py")
W, H = 400, 240


class base:
    """zynthian_widget_base as the panel widget uses it: its control screen, its size, shown."""

    def __init__(self, parent):
        self.zyngui_control, self.processor = parent, None
        self.width, self.height, self.shown = W, H, True

    def set_processor(self, processor):
        self.processor = processor

    def update(self):
        if self.shown:
            self.refresh_gui()


class NoTouchDevice(Exception):
    pass


def no_touch():
    raise NoTouchDevice("none here")


def load_widget():
    """zyngui/zynthian_widget_omx_panel.py over the real gestures and panel view; (its module, the modules it saw)."""
    engine = types.ModuleType("zyngine")
    engine.__path__ = [os.path.join(ROOT, "zyngine")]
    config = stand_in("zyngui.zynthian_gui_config", color_bg="#000000", color_tx="#ffffff", color_tx_off="#888888",
                      color_on="#ff0000")
    modules = {
        "tkinter": mock.MagicMock(), "PIL": mock.MagicMock(), "zyngine": engine,
        "zyngine.zynthian_touch_layer": stand_in("t", EvdevSource=no_touch, NoTouchDevice=NoTouchDevice),
        "zyngui": stand_in("zyngui", __path__=[os.path.join(ROOT, "zyngui")], zynthian_gui_config=config),
        "zyngui.zynthian_gui_config": config,
        "zyngui.zynthian_widget_base": stand_in("b", zynthian_widget_base=base),
    }
    for name in ("zyngine.zynthian_omx_panel_view", "zyngine.zynthian_panel_gestures", "zyngine.zynthian_position_law",
                 "zyngui.zynthian_gui_omx_panel_image"):
        modules[name] = None  # this tree's own, imported afresh
    with mock.patch.dict(sys.modules, modules):
        for name in [n for n, m in modules.items() if m is None]:
            del sys.modules[name]
        spec = importlib.util.spec_from_file_location("zynthian_widget_omx_panel", WIDGET)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class Controller:
    """A control as the panel reads it: a linear travel of 0..1 and its value."""

    def __init__(self, symbol, group):
        self.symbol, self.group_symbol, self.short_name, self.name = symbol, group, symbol, symbol
        self.is_path, self.path_file_types = False, None
        self.ticks = self.labels = self.position_law = None
        self.is_toggle = self.is_integer = self.is_logarithmic = self.readonly = self.is_dirty = False
        self.value, self.value_min, self.value_max, self.value_default = 0.5, 0.0, 1.0, 0.5

    def set_value(self, value):
        self.value = value

    def get_value2label(self):
        return str(self.value)


class GuiController:
    """One of the screen's four controller widgets: the slot's controller, or None."""

    def __init__(self):
        self.zctrl, self.plotted = None, 0

    def config(self, zctrl):
        self.zctrl = zctrl

    def show(self):
        pass

    def calculate_plot_values(self):
        pass

    def plot_value(self):
        self.plotted += 1


class FakeView:
    """The renderer's view: the part of the panel it was opened with, and what it was given."""
    opened = []

    def __init__(self, part, look=None):
        self.symbols, self.meters, self.values, self.drew = list(part["keys"]), [], {}, 0
        self.look = look  # the UI look the widget opens the view with (#70)
        FakeView.opened.append(self)

    def set_title(self, *a): pass
    def set_surface(self, *a): pass
    def set_travel(self, *a): pass
    def close(self): pass
    def set_value(self, i, fraction, text): self.values[self.symbols[i]] = fraction

    def draw(self, w, h):
        self.drew += 1
        return bytes(w * h * 4), None


class BlankSlotPage(unittest.TestCase):
    """HPF 2 is [blank, hpf_mix, blank, blank]; HPF is four controls (tests/test_control_short_pages.py PAGES)."""

    def setUp(self):
        self.module = load_widget()
        self.proc = processor(PAGES)
        self.zctrls = {k: Controller(k, z.group_symbol) for k, z in self.proc.controllers_dict.items()}
        self.proc.controllers_dict = self.zctrls
        with mock.patch("zyngine.zynthian_processor.zynsigman", mock.MagicMock(), create=True):
            self.proc.init_ctrl_screens()
        self.proc.id = 1
        self.proc.engine.custom_gui_fpath = WIDGET
        self.proc.engine.zctrls = self.zctrls
        self.proc.engine.drawn = None
        self.proc.engine.curve, self.proc.engine.meter = (lambda display: []), (lambda symbol: None)
        self.proc.engine.curve_drawing = lambda display: ([], None)
        control = load_control()
        screen = object.__new__(control)
        screen.mode, screen.widgets, screen.current_widget, screen.widget_zctrl = "control", {}, None, None
        # zynthian_gui_control's widget cache: by file path, with the file's (mtime_ns, size), so this stub is the one used
        st = os.stat(WIDGET)
        screen.modules = {WIDGET: (self.module, (st.st_mtime_ns, st.st_size))}
        screen.zyngui = mock.MagicMock()
        screen.zyngui.get_current_processor.return_value = self.proc
        screen.chain_manager = types.SimpleNamespace(processors={1: self.proc})
        screen.parent = None
        screen.configure_processors = lambda curproc: setattr(screen, "processors", [self.proc])
        screen.zgui_controllers = [GuiController() for _ in range(4)]
        screen.swipe_update = lambda: None  # the selector's, a stand-in here
        screen.index = 0
        screen.fill_list()
        self.screen = screen

    def open(self, page):
        """The page chosen in the screen's list, as zynthian_gui_control.select does after the selector moved, and
        one refresh of the screen as the UI's plot task runs it (forced, as chain control forces it)."""
        self.screen.index = next(i for i, row in enumerate(self.screen.list_data) if row[0] is not None and row[2] == page)
        self.screen.set_controller_screen()
        self.screen.plot_zctrls(force=True)
        (widget,) = self.screen.widgets.values()
        return widget

    def slots(self):
        return [g.zctrl and g.zctrl.symbol for g in self.screen.zgui_controllers]

    def test_the_strips_of_a_page_with_a_blank_slot_and_then_another_page(self):
        widget = self.open("HPF 2")
        self.assertEqual(self.slots(), [None, "hpf_mix", None, None])
        rows = widget.panel.rows
        self.assertEqual([z.symbol for z, _ in rows], ["hpf_mix"])
        self.assertEqual(rows[0][1].target, (0, H / 4, W, H / 4), "the strip is in its own slot's row, the second of four")
        self.assertIsNone(widget.panel.row_at(H / 8), "a press on the blank slot's row lands on no strip")
        widget = self.open("HPF")
        self.assertEqual(self.slots(), ["hpf_on", "hpf_freq", "hpf_q", "hpf_slope"])
        self.assertEqual([(z.symbol, g.target[1]) for z, g in widget.panel.rows],
                         [("hpf_on", 0), ("hpf_freq", H / 4), ("hpf_q", H / 2), ("hpf_slope", 3 * H / 4)])
        widget = self.open("Meters")
        self.assertEqual(self.slots(), [None, None, None, None])
        self.assertEqual(widget.panel.rows, [], "a page of blank slots draws no strip")

    def test_the_renderers_part_of_a_page_with_a_blank_slot_and_then_another_page(self):
        self.proc.engine.drawn = ({"controls": []},)
        FakeView.opened = []
        for module, name, value in ((self.module.panel_view, "View", FakeView),
                                    (self.module.panel_view, "screen_part",
                                     lambda layout, keys: ({"keys": sorted(keys)}, {})),
                                    (self.module.panel_image, "PanelImage", mock.MagicMock())):
            patch = mock.patch.object(module, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        widget = self.open("HPF 2")
        self.assertEqual(self.slots(), [None, "hpf_mix", None, None])
        self.assertEqual(widget.drawn.symbols, ["hpf_mix"], "the page's control and no other")
        self.assertEqual(widget.drawn.values, {"hpf_mix": 0.5})
        self.assertEqual(widget.drawn.drew, 1)
        widget = self.open("HPF")
        self.assertEqual(widget.drawn.symbols, ["hpf_freq", "hpf_on", "hpf_q", "hpf_slope"])
        self.assertEqual(widget.drawn.drew, 1)
        self.assertEqual(len(FakeView.opened), 2)

    def test_a_forced_refresh_plots_the_controls_and_passes_the_blank_slots(self):
        self.open("HPF 2")
        self.assertEqual([g.plotted for g in self.screen.zgui_controllers], [0, 1, 0, 0])


if __name__ == "__main__":
    unittest.main()
