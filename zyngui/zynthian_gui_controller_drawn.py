#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian GUI
#
# Zynthian GUI Controller, drawn by omx-panel's renderer (docs/ui-look-drawn-widgets.md, zynthian-ui#53)
#
# The stock controller widget drawn as the OpenMixer console draws a control: one panel description of one control
# per controller, given to the renderer every OpenMixer surface draws a panel with (zynthian_omx_panel_view), its RGBA
# painted over the panel colour as one canvas image. A numeric controller is the renderer's knob, a list of values its
# selector, a two-value list its switch, a path or a selector counter its glass display; the label and the value are
# the renderer's; the selection is a frame in the colour the stock arc would take (a host's chrome, not a colour role).
# The look the view is opened in is the UI's palette over the renderer's own (zynthian_ui_look).
#
# drawn_controller(base) makes the class over the stock one, overriding only what paints: show, on_size, plot_value,
# set_title and _set_color_graph. The zynpot, the touch gestures, the value's formatting and travel, the MIDI bind text
# are the stock widget's code, inherited. Without the renderer the stock widget is drawn and the reason said once.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import logging
import tkinter

from zyngine import zynthian_omx_panel_view as panel_view
from zyngine import zynthian_ui_look as ui_look
from zyngui import zynthian_gui_config

FRAME_PX = 2
SECTION_KEY = "controller"


def widget_kind(zctrl, selector_counter):
    """The renderer's standard widget for a stock controller: what upstream draws as an arc, a list or a text."""
    if selector_counter or zctrl.is_path:
        return "display"
    if zctrl.ticks:
        return "switch" if len(zctrl.ticks) == 2 else "selector"
    return "knob"


def description(symbol, label, kind):
    """One control in one section, in the renderer's own grammar (`omx-panel layout`): nothing it does not read."""
    return {"sections": [{"key": SECTION_KEY, "label": ""}],
            "controls": [{"symbol": str(symbol), "label": str(label), "section": 0, "standard": {"widget": kind}}]}


def drawn_controller(base):
    """The look's controller class over the stock <base> (zynthian_gui_controller)."""

    class zynthian_gui_controller_drawn(base):
        said = False  # the renderer's absence, said once for every controller
        look = None  # the look document, read once per class from the renderer's tools directory
        look_read = False

        def __init__(self, *args, **kwargs):
            self.view = None
            self.view_key = None
            self.drawn_state = None
            self.image = None
            self.image_item = None
            self.frame_item = None
            self.frame_color = None
            self.stock = False  # True once the renderer refused or stopped: the stock items draw
            super().__init__(*args, **kwargs)

        # ---- what paints, over the stock widget's own computations

        def show(self):
            super().show()
            self.draw()

        def on_size(self, event):
            super().on_size(event)
            self.draw()

        def plot_value(self):
            refresh = self.shown and self.zctrl and self.refresh_plot_value
            super().plot_value()
            if refresh:
                self.draw()

        def set_title(self, title):
            super().set_title(title)
            self.draw()

        def _set_color_graph(self, color):
            super()._set_color_graph(color)
            self.frame_color = None if color == zynthian_gui_config.color_ctrl_bg_on else color
            self.draw()

        # ---- the renderer

        def draw(self):
            if self.hidden or not self.shown or self.zctrl is None or self.stock:
                return
            w, h = self.winfo_width(), self.winfo_height()
            if w < 2 or h < 2:
                return
            kind = widget_kind(self.zctrl, self.selector_counter)
            key = (kind, self.zctrl.symbol, self.title, w, h)
            if self.view is None or self.view_key != key:
                if not self.open_view(kind, key, w, h):
                    return
            state = (self.value_plot, self.value_print, self.frame_color)
            if state != self.drawn_state or self.image is None:
                self.drawn_state = state
                try:
                    self.give_reading(kind)
                    pixels = self.view.draw(w, h)
                except panel_view.RendererAbsent as e:
                    self.fall_back(e)
                    return
                self.paint(pixels, w, h)
            self.itemconfig('gui', state=tkinter.HIDDEN)
            self.frame()

        def open_view(self, kind, key, w, h):
            if self.view:
                self.view.close()
                self.view = None
            self.drawn_state = None
            cls = type(self)
            if not cls.look_read:
                cls.look_read = True
                cls.look = ui_look.look_for(zynthian_gui_config, panel_view.tools_dir())
            try:
                view = panel_view.View(description(self.zctrl.symbol, self.title, kind), look=cls.look)
                view.set_title("", "")
                view.set_surface(w, h)
                if kind == "knob" and not self.zctrl.ticks:
                    z = self.zctrl
                    view.set_travel(0, z.value_min, z.value_max, z.value_default, (z.position_law or {}).get("step", 0.0),
                                    bool(z.is_logarithmic), bool(z.is_integer))
            except panel_view.RendererAbsent as e:
                self.fall_back(e)
                return False
            self.view, self.view_key = view, key
            return True

        def give_reading(self, kind):
            """The stock widget's own reading (calculate_plot_values) as the renderer takes it."""
            z = self.zctrl
            if kind == "selector":
                self.view.set_choice(0, z.get_value2index(), len(z.ticks), self.value_print)
            elif kind == "display":
                self.view.set_value(0, 0, self.value_print)
            else:
                self.view.set_value(0, self.value_plot, self.value_print)

        def paint(self, pixels, w, h):
            from PIL import Image
            rgba = Image.frombuffer("RGBA", (w, h), pixels, "raw", "RGBA", 0, 1)
            back = Image.new("RGBA", (w, h), zynthian_gui_config.color_panel_bg)
            self.image = Image.alpha_composite(back, rgba)
            self.show_image(self.image)

        def show_image(self, image):
            self.photo = self.photo_of(image)
            if self.image_item is None:
                self.image_item = self.create_image(0, 0, anchor=tkinter.NW, image=self.photo)
            else:
                self.itemconfig(self.image_item, image=self.photo)

        def photo_of(self, image):
            """The Tk photo of a PIL image: the one call that needs a display."""
            from PIL import ImageTk
            return ImageTk.PhotoImage(image)

        def frame(self):
            """The selection: a frame around the face in the colour the stock arc would take; none when unselected."""
            w, h = self.winfo_width(), self.winfo_height()
            if self.frame_item is None:
                self.frame_item = self.create_rectangle(FRAME_PX // 2, FRAME_PX // 2, w - FRAME_PX, h - FRAME_PX,
                                                        outline="", width=FRAME_PX, state=tkinter.HIDDEN)
            self.coords(self.frame_item, FRAME_PX // 2, FRAME_PX // 2, w - FRAME_PX, h - FRAME_PX)
            if self.frame_color:
                self.itemconfig(self.frame_item, outline=self.frame_color, state=tkinter.NORMAL)
            else:
                self.itemconfig(self.frame_item, state=tkinter.HIDDEN)

        def fall_back(self, why):
            """The renderer refused or stopped: the stock items draw, said once."""
            self.stock = True
            if self.view:
                try:
                    self.view.close()
                except Exception:
                    pass
                self.view = None
            if self.image_item is not None:
                self.delete(self.image_item)
                self.image_item = None
            if self.frame_item is not None:
                self.itemconfig(self.frame_item, state=tkinter.HIDDEN)
            self.image = None
            self.itemconfig('gui', state=tkinter.NORMAL)
            cls = type(self)
            if not cls.said:
                cls.said = True
                logging.warning("%s: the controllers are drawn stock", why)

    return zynthian_gui_controller_drawn
