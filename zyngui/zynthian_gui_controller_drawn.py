#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian GUI
#
# Zynthian GUI Controller, drawn by omx-panel's renderer (docs/ui-look-drawn-widgets.md, zynthian-ui#53)
#
# The stock controller widget drawn as the OpenMixer console draws a control: one panel description of one control
# per controller, given to omx-panel's renderer (zynthian_omx_panel_view), its RGBA
# painted over the panel colour as one canvas image. A numeric controller is the renderer's knob, a list of values its
# selector, a two-value list its switch, a path or a selector counter its glass display; the label and the value are
# the renderer's; the selection is a frame in the colour the stock arc would take (a host's chrome, not a colour role).
# The operator's state stays the stock widget's items, above the image: the MIDI-bind text as upstream draws it, and
# the pickup marker, moved onto the renderer's knob (its target rect) over the knob's 270 degree travel. The look the
# view is opened in is the UI's palette over the renderer's own (zynthian_ui_look).
#
# drawn_controller(base) makes the class over the stock one, overriding only what paints: show, on_size, plot_value,
# set_title, _set_color_graph and zynpot_abs (the marker's place), and config, where a page begins. The zynpot, the
# touch gestures, the value's formatting and travel, the MIDI bind text are the stock widget's code, inherited.
# Without the renderer, or with a look the table cannot value, the stock widget is drawn and the reason said once. A
# renderer that stopped is another matter (zynthian-ui#79): the stock widget is drawn on the page it stopped on, and
# the next page (config) is drawn in the look again, the renderer started again by its view
# (zynthian_omx_panel_view, which gives up a renderer that stops at every start).
#
# The renderer's calls are Tk's thread's: a page change or an encoder's move that comes from another thread (the CUIA
# thread) gives its draw to Tk's thread (after_idle), one draw however many times it asks, so the plot task never
# draws a view the page change is closing.
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
MARKER_PX = 2  # the pickup marker's distance from the knob's rim
MARKER_DEG = 12  # the marker's width, upstream's
KNOB_DEG = 270  # the renderer's knob travel (view.c draw_knob: -135 to +135 degrees)
SECTION_KEY = "controller"


def widget_kind(zctrl, selector_counter):
    """The renderer's standard widget for a stock controller: what upstream draws as an arc, a list or a text."""
    if selector_counter or zctrl.is_path:
        return "display"
    if zctrl.ticks:
        # two values are a switch unless the engine said they are no toggle (an lv2 enumeration of two scale points, such as
        # Polyphony's 8 and 32 voices, zynthian-ui#86); a list that came with no word on toggles keeps the controller's own rule
        return "switch" if len(zctrl.ticks) == 2 and zctrl.toggle_declared is not False else "selector"
    return "knob"


def description(symbol, label, kind):
    """One control in one section, in the renderer's own grammar (`omx-panel layout`): nothing it does not read."""
    return {"sections": [{"key": SECTION_KEY, "label": ""}],
            "controls": [{"symbol": str(symbol), "label": str(label), "section": 0, "standard": {"widget": kind}}]}


def drawn_controller(base):
    """The look's controller class over the stock <base> (zynthian_gui_controller)."""

    class zynthian_gui_controller_drawn(base):
        said = False  # the renderer's absence, or a look the table cannot value: said once for every controller

        def __init__(self, *args, **kwargs):
            self.view = None
            self.view_key = None
            self.drawn_state = None
            self.image = None
            self.image_item = None
            self.frame_item = None
            self.frame_color = None
            self.stock = False  # True once the renderer refused or stopped: the stock items draw
            self.stopped = False  # the stock items draw because the renderer stopped: until the next page
            self.draw_due = False  # a draw asked from another thread waits for Tk's
            super().__init__(*args, **kwargs)

        # ---- what paints, over the stock widget's own computations

        def config(self, zctrl):
            if self.stopped:  # a new page: the renderer that stopped is started again by the view draw() opens
                self.stock = self.stopped = False
            super().config(zctrl)

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

        def zynpot_abs(self, val):
            super().zynpot_abs(val)
            if self.zctrl and self.pickup and self.view and not self.stock and self.graph_type == self.GUI_CTRL_ARC:
                if panel_view.in_owner_thread():
                    self.place_marker(val)
                else:
                    self.after_idle(self.place_marker, val)

        # ---- the renderer

        def draw(self):
            if not panel_view.in_owner_thread():
                if not self.draw_due:
                    self.draw_due = True
                    self.after_idle(self.draw)
                return
            self.draw_due = False
            z = self.zctrl  # read once: a page change in another thread may set the next one under this draw
            if z is None and not self.stock:
                self.blank()
            if self.hidden or not self.shown or z is None or self.stock:
                return
            w, h = self.winfo_width(), self.winfo_height()
            if w < 2 or h < 2:
                return
            kind = widget_kind(z, self.selector_counter)
            key = (kind, z.symbol, self.title, w, h)
            if self.view is None or self.view_key != key:
                if not self.open_view(z, kind, key, w, h):
                    return
            state = (self.value_plot, self.value_print, self.frame_color)
            if state != self.drawn_state or self.image is None:
                self.drawn_state = state
                try:
                    self.give_reading(z, kind)
                    pixels = self.view.draw(w, h)
                except panel_view.RendererAbsent as e:
                    self.fall_back(e)
                    return
                self.paint(pixels, w, h)
            for item in (self.graph, self.label_title, self.value_text):  # the renderer draws these; the MIDI bind stays
                self.itemconfig(item, state=tkinter.HIDDEN)
            self.frame()

        def open_view(self, z, kind, key, w, h):
            if self.view:
                self.view.close()
                self.view = None
            self.drawn_state = None
            try:
                look = ui_look.look_for(zynthian_gui_config, panel_view.tools_dir())
                view = panel_view.View(description(z.symbol, self.title, kind), look=look)
                view.set_title("", "")
                view.set_surface(w, h)
                if kind == "knob" and not z.ticks:
                    view.set_travel(0, z.value_min, z.value_max, z.value_default, (z.position_law or {}).get("step", 0.0),
                                    bool(z.is_logarithmic), bool(z.is_integer))
            except (panel_view.RendererAbsent, ui_look.LookShort) as e:
                self.fall_back(e)
                return False
            self.view, self.view_key = view, key
            return True

        def place_marker(self, val):
            """Upstream's pickup marker (graph_pickup, an arc) on the renderer's knob: its target rect is the knob's
            bounding square; the encoder's place over the knob's travel, from the top. None: no knob, no marker."""
            if not self.view or self.stock:  # the page changed before Tk's thread came to it
                return
            try:
                rect = self.view.target_rect(0)
            except panel_view.RendererAbsent as e:
                self.fall_back(e)
                return
            if not rect:
                self.itemconfig(self.graph_pickup, state=tkinter.HIDDEN)
                return
            (x, y, w, h), _ = rect
            cx, cy, r = x + w / 2, y + h / 2, h / 2
            self.coords(self.graph_pickup, cx - r - MARKER_PX, cy - r - MARKER_PX, cx + r + MARKER_PX, cy + r + MARKER_PX)
            # Tk's arc angles run counter-clockwise from 3 o'clock; the knob's from 12 o'clock, clockwise
            self.itemconfig(self.graph_pickup, start=90 + KNOB_DEG / 2 - KNOB_DEG * val - MARKER_DEG / 2, extent=MARKER_DEG,
                            width=max(2, int(r * 0.1)), outline=zynthian_gui_config.color_ctrl_tx_off)

        def give_reading(self, z, kind):
            """The stock widget's own reading (calculate_plot_values) as the renderer takes it."""
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
                self.tag_raise(self.midi_bind)  # the operator's state, above the face
                self.tag_raise(self.graph_pickup)
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

        def blank(self):
            """A blank slot (no controller): the last controller's face, frame and view go; the stock widget hides
            its own items."""
            if self.view:
                try:
                    self.view.close()
                except panel_view.RendererAbsent:
                    pass
                self.view = self.view_key = None
            if self.image_item is not None:
                self.delete(self.image_item)
                self.image_item = None
            if self.frame_item is not None:
                self.itemconfig(self.frame_item, state=tkinter.HIDDEN)
            self.image = self.drawn_state = None

        def fall_back(self, why):
            """The renderer refused or stopped, or the look cannot be valued: the stock items draw, said once."""
            self.stock = True
            self.stopped = isinstance(why, panel_view.RendererStopped)
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
