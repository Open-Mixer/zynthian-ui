# -*- coding: utf-8 -*-
#
# zyngui/zynthian_widget_omx_panel.py loaded over stand-ins (Tk, PIL, the gesture table, the touch layer, the base
# widget) and the real panel view and look modules: the harness tests/test_omx_panel_renderer_crash.py and
# tests/test_ui_look_widgets.py share. Not a test module: unittest does not collect it.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import sys
import types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VIEW = os.path.join(ROOT, "zyngine", "zynthian_omx_panel_view.py")
LOOK = os.path.join(ROOT, "zyngine", "zynthian_ui_look.py")
IMAGE = os.path.join(ROOT, "zyngui", "zynthian_gui_omx_panel_image.py")
WIDGET = os.path.join(ROOT, "zyngui", "zynthian_widget_omx_panel.py")


def stand_in(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


def load_widget(**config_values):
    """zyngui/zynthian_widget_omx_panel.py and the real panel view module it reads RendererStopped from, with
    zynthian_gui_config a stand-in carrying <config_values> over a stock palette."""
    spec = importlib.util.spec_from_file_location("panel_view_under_test", VIEW)
    panel_view = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(panel_view)

    class base:
        def __init__(self, parent):
            # shown: zynthian_widget_base's flag, which the widget reads to start the spectrum of a shown panel
            self.width, self.height, self.processor, self.shown = 1, 1, None, False

        def set_processor(self, processor):
            self.processor = processor

    class NoTouchDevice(Exception):
        pass

    def no_touch():
        raise NoTouchDevice("none here")

    spec = importlib.util.spec_from_file_location("panel_image_under_test", IMAGE)
    panel_image = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(panel_image)
    spec = importlib.util.spec_from_file_location("ui_look_under_test", LOOK)
    ui_look = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ui_look)
    zyngine = stand_in("zyngine", __path__=[], zynthian_omx_panel_view=panel_view, zynthian_ui_look=ui_look)
    config = stand_in("zyngui.zynthian_gui_config", **{"color_bg": "#000000", "color_tx": "#ffffff", "color_tx_off": "#888888",
                                                       "color_on": "#ff0000", **config_values})
    modules = {
        "tkinter": mock.MagicMock(), "PIL": mock.MagicMock(), "zyngine": zyngine,
        "zyngine.zynthian_omx_panel_view": panel_view, "zyngine.zynthian_ui_look": ui_look,
        "zyngine.zynthian_panel_gestures": stand_in("g", Panel=mock.MagicMock(), GestureTableAbsent=type("A", (Exception,), {})),
        "zyngine.zynthian_position_law": stand_in("p"),
        "zyngine.zynthian_touch_layer": stand_in("t", EvdevSource=no_touch, NoTouchDevice=NoTouchDevice),
        "zyngui": stand_in("zyngui", __path__=[], zynthian_gui_config=config, zynthian_gui_omx_panel_image=panel_image),
        "zyngui.zynthian_gui_config": config,
        "zyngui.zynthian_gui_omx_panel_image": panel_image,
        "zyngui.zynthian_widget_base": stand_in("b", zynthian_widget_base=base),
    }
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("zynthian_widget_omx_panel_under_test", WIDGET)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.__dict__["Image"] = None
    return module, panel_view, modules
