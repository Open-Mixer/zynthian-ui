#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian GUI Controller, drawn with Tk and PIL (docs/ui-look-tk-widgets.md, zynthian-ui#93)
#
# The vintage look of the stock controller widget, drawn by Zynthian's own toolkit: Tk, and PIL for what Tk's canvas
# cannot do (gradients, anti-aliasing). Nothing of omx-panel's drawing is read: the proportions are written here, from
# the look's colour tokens (zynthian_gui_config: the knob's metal and the pill, set by the vintage preset). From
# omx-panel only behaviour comes, and not through this module: the kind of a control is the gesture module's
# widget_of (the one switch rule), the position of the value is the stock widget's (value_plot, from the position
# law of python3-omx-contract).
#
#   knob      numeric: one PIL face (tick ring, shade, rim, knurl, cap) per size and token set, three canvas lines
#             for the carved pointer, moved by coords
#   switch    a two-value toggle: a pill (two ovals and a rectangle) and a thumb, moved by coords
#   selector  more than two values: a rounded strip, the chosen segment moved by coords
#   display   a path or a selector counter: the glass, a PIL image per size, the value in the on colour
#
# The stock widget's items stay: the label, the value text, the MIDI bind and the pickup marker keep upstream's fonts
# and fitting; the stock arc is not shown. The look adds items and never re-implements text. A value that changes
# only moves items (coords, itemconfig): no image, no face. The faces are built when the size or the tokens change
# (on_size, show) and cached. The widget keeps the stock widget's threading: nothing here is drawn from a thread but
# Tk's (the plot task); a value set from another one only marks the controller dirty, as upstream does.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import math
import tkinter

from zyngine import zynthian_panel_gestures
from zyngui import zynthian_gui_config

FRAME_PX = 2
MARKER_PX = 2  # the pickup marker's distance from the knob's tick ring
MARKER_DEG = 12  # the marker's width, upstream's
KNOB_DEG = 270  # the knob's travel, -135 to +135 degrees from 12 o'clock

# Zynthian's own proportions, in radii of the knob (checked against a picture, docs/ui-look-tk-widgets.md section 2)
TICK_OUT, TICK_IN = 0.97, 0.86
RIM = 0.81
KNURL = 0.73
CAP = 0.70
POINTER_FROM, POINTER_TO = 0.21, 0.63
CAP_FOCUS = (0.35, 0.3)  # where the cap's highlight sits, in the cap's box
CAP_STEPS = 24  # concentric discs of the cap's gradient
KNURL_LINES = 24
SUPERSAMPLE = 3

# the colours a face is drawn from: part of its cache key
FACE_TOKENS = ("color_knob_face", "color_knob_edge", "color_knob_cap_hi", "color_knob_knurl", "color_hl", "color_panel_bg",
               "color_off", "color_panel_hl")

FACES = {}  # (kind, size, tokens) -> PIL image: built once
BUILDS = []  # what was built, for the test that holds "once per size"


def widget_kind(zctrl, selector_counter):
    """What a stock controller is drawn as. The rule is the gesture table's (zynthian_panel_gestures.widget_of): the
    drawing and the gestures cannot disagree on a control. A path or a selector counter is the glass."""
    if selector_counter or zctrl.is_path:
        return "display"
    return {"switch": "switch", "selector": "selector", "fader": "knob"}[zynthian_panel_gestures.widget_of(zctrl)]


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def knob_face(size, tokens):
    """The knob's face: <size> px square, opaque over the panel colour. <tokens> is a tuple of (name, colour) pairs
    (FACE_TOKENS); drawn at SUPERSAMPLE x and reduced, once per (size, tokens)."""
    key = ("knob", size, tokens)
    if key in FACES:
        return FACES[key]
    from PIL import Image, ImageColor, ImageDraw
    t = {k: ImageColor.getrgb(v)[:3] for k, v in tokens}
    S = size * SUPERSAMPLE
    c = S / 2
    r = S / 2

    def disc(draw, radius, fill, dx=0.0, dy=0.0):
        draw.ellipse((c + dx - radius, c + dy - radius, c + dx + radius, c + dy + radius), fill=fill)

    def spoke(draw, deg, r0, r1, fill, width):
        a = math.radians(deg)
        draw.line((c + math.sin(a) * r0 * r, c - math.cos(a) * r0 * r, c + math.sin(a) * r1 * r, c - math.cos(a) * r1 * r),
                  fill=fill, width=width)

    im = Image.new("RGBA", (S, S), t["color_panel_bg"] + (255,))
    shade = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    disc(ImageDraw.Draw(shade), RIM * r, (0, 0, 0, 128), dy=S / 48)
    im = Image.alpha_composite(im, shade)
    d = ImageDraw.Draw(im)
    tick = max(SUPERSAMPLE, int(S * 0.018))
    for i in range(11):
        spoke(d, -135 + 27 * i, TICK_IN, TICK_OUT, t["color_hl"], tick)
    disc(d, RIM * r, t["color_knob_edge"])
    disc(d, KNURL * r, t["color_knob_knurl"])
    for i in range(KNURL_LINES):
        spoke(d, 15 * i, CAP, KNURL, t["color_knob_edge"], max(1, SUPERSAMPLE // 2))
    # the cap: a radial gradient as concentric discs, each one smaller, nearer the focus and lighter than the last
    fx, fy = (CAP_FOCUS[0] - 0.5) * 2 * CAP * r, (CAP_FOCUS[1] - 0.5) * 2 * CAP * r
    for i in range(CAP_STEPS):
        u = i / (CAP_STEPS - 1)
        disc(d, CAP * r * (1 - 0.95 * u), _mix(t["color_knob_face"], t["color_knob_cap_hi"], u), dx=fx * u, dy=fy * u)
    face = im.resize((size, size), Image.BOX).convert("RGB")
    FACES[key] = face
    BUILDS.append(key)
    return face


def glass_face(width, height, tokens):
    """The display's glass: a recessed screen, <width> x <height>, two stepped insets and a 12 px grid at a tenth of
    the legend colour, opaque over the panel colour."""
    key = ("glass", (width, height), tokens)
    if key in FACES:
        return FACES[key]
    from PIL import Image, ImageColor, ImageDraw
    t = {k: ImageColor.getrgb(v)[:3] for k, v in tokens}
    im = Image.new("RGB", (width, height), t["color_panel_bg"])
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, width - 1, height - 1), fill=_mix(t["color_panel_bg"], (0, 0, 0), 0.5))
    d.rectangle((1, 1, width - 2, height - 2), fill=_mix(t["color_off"], (0, 0, 0), 0.25))
    d.rectangle((2, 2, width - 3, height - 3), fill=t["color_off"])
    grid = _mix(t["color_off"], t["color_hl"], 0.1)
    for x in range(14, width - 2, 12):
        d.line((x, 3, x, height - 4), fill=grid)
    for y in range(14, height - 2, 12):
        d.line((3, y, width - 4, y), fill=grid)
    FACES[key] = im
    BUILDS.append(key)
    return im


def tokens():
    return tuple(sorted((k, getattr(zynthian_gui_config, k)) for k in FACE_TOKENS))


def tk_look(base):
    """The look's controller class over the stock <base> (zynthian_gui_controller)."""

    class zynthian_gui_controller_tk(base):

        def __init__(self, *args, **kwargs):
            self.kind = None
            self.parts = []  # the canvas items this look added, bottom first
            self.part = {}
            self.built = None  # what the parts were built for
            self.frame_item = None
            self.frame_color = None
            super().__init__(*args, **kwargs)

        # ---- what paints, over the stock widget's own computations; all on Tk's thread

        def show(self):
            super().show()
            self.draw()

        def on_size(self, event):
            super().on_size(event)  # puts the stock arc's items where upstream has them
            self.built = None  # ours go back where the look has them: from the cache, no face is drawn again
            self.draw()

        def plot_value(self):
            refresh = self.shown and self.zctrl and self.refresh_plot_value
            super().plot_value()
            if refresh:
                self.draw()

        def _set_color_graph(self, color):
            super()._set_color_graph(color)
            self.frame_color = None if color == zynthian_gui_config.color_ctrl_bg_on else color
            self.frame()

        def zynpot_abs(self, val):
            super().zynpot_abs(val)
            if self.zctrl and self.pickup and self.kind == "knob" and self.graph_type == self.GUI_CTRL_ARC:
                self.itemconfig(self.graph_pickup, start=90 + KNOB_DEG / 2 - KNOB_DEG * val - MARKER_DEG / 2, extent=MARKER_DEG)

        # ---- the drawing

        def geometry(self):
            """The stock arc's box (on_size_arc): the centre and the radius the knob takes."""
            ww, hh = self.winfo_width(), self.winfo_height()
            radius = min(ww, hh) // 2
            if radius > 4:
                radius -= 4
            arc_width = radius // 4
            if self.vertical:
                x0, y0 = ww // 2, hh - radius + arc_width - 4
            else:
                x0, y0 = ww - radius - 2, hh // 2
                if self.selector_counter:
                    y0 -= radius // 3 + 2
            return x0, y0, radius

        def draw(self):
            if self.hidden:
                return
            z = self.zctrl  # read once
            if z is None:
                self.clear()
                return
            if not self.shown:
                return
            ww, hh = self.winfo_width(), self.winfo_height()
            if ww < 2 or hh < 2:
                return
            kind = widget_kind(z, self.selector_counter)
            built = (kind, ww, hh, self.vertical, self.selector_counter, tokens(), len(z.ticks or ()) if kind == "selector" else 0)
            if built != self.built:
                self.build(kind, built)
            self.itemconfig(self.graph, state=tkinter.HIDDEN)
            getattr(self, "move_" + kind)(z)
            self.frame()

        def clear(self):
            for item in self.parts:
                self.delete(item)
            self.parts, self.part, self.built, self.kind = [], {}, None, None
            if self.frame_item is not None:
                self.itemconfig(self.frame_item, state=tkinter.HIDDEN)

        def build(self, kind, built):
            """The items of <kind> for this size and these tokens: the faces from the cache, nothing per value."""
            self.clear()
            self.kind, self.built = kind, built
            getattr(self, "build_" + kind)(*self.geometry())
            for item in reversed(self.parts):  # ours below the stock items: text, MIDI bind, pickup marker
                self.tag_lower(item)
            self.itemconfig(self.value_text, fill=zynthian_gui_config.color_on if kind == "display"
                            else zynthian_gui_config.color_ctrl_tx)

        def add(self, name, item):
            self.parts.append(item)
            self.part[name] = item
            return item

        def show_image(self, name, image, x, y):
            photo = self.photo_of(image)
            setattr(self, "photo_" + name, photo)  # Tk keeps no reference to the photo
            self.add(name, self.create_image(x, y, anchor=tkinter.NW, image=photo))

        def photo_of(self, image):
            """The Tk photo of a PIL image: the one call that needs a display."""
            from PIL import ImageTk
            return ImageTk.PhotoImage(image)

        # -- the knob

        def build_knob(self, x0, y0, radius):
            self.centre = (x0, y0, radius)
            self.show_image("face", knob_face(2 * radius, tokens()), x0 - radius, y0 - radius)
            wall = max(1, round(radius * 0.025))
            width = max(2, round(radius * 0.05))
            self.add("shade", self.create_line(0, 0, 0, 0, fill=_shade(zynthian_gui_config.color_knob_edge, 0.0), width=width + 1,
                                               capstyle=tkinter.ROUND))
            self.add("lit", self.create_line(0, 0, 0, 0, fill=_lighter(zynthian_gui_config.color_knob_cap_hi), width=width,
                                             capstyle=tkinter.ROUND))
            self.add("pointer", self.create_line(0, 0, 0, 0, fill=zynthian_gui_config.color_knob_pointer, width=width,
                                                 capstyle=tkinter.ROUND))
            self.wall = wall
            z = self.zctrl
            if z.value_range and z.value_min < 0 <= z.value_max and not z.is_logarithmic and not z.position_law:
                self.add("zero", self.create_line(0, 0, 0, 0, fill=zynthian_gui_config.color_on, width=max(2, width - 1)))
            # the pickup marker: just outside the tick ring, over the pointer's own travel
            m = TICK_OUT * radius + MARKER_PX
            self.coords(self.graph_pickup, x0 - m, y0 - m, x0 + m, y0 + m)
            self.itemconfig(self.graph_pickup, width=max(2, int(radius * 0.03)), outline=zynthian_gui_config.color_ctrl_tx_off)

        def fraction(self, z):
            """Where the pointer stands on the 270 degrees: the stock plot, which a bipolar control measures from its
            zero (the arc's way), put back to the travel's own 0..1."""
            plot = self.value_plot
            if z.position_law is None and not z.is_logarithmic and not z.ticks and z.value_range and z.value_min < 0:
                plot -= z.value_min / z.value_range
            return min(1.0, max(0.0, plot))

        def move_knob(self, z):
            x0, y0, radius = self.centre
            a = math.radians(-KNOB_DEG / 2 + KNOB_DEG * self.fraction(z))
            sx, sy = math.sin(a), -math.cos(a)  # the pointer's direction; its walls are one pixel either side
            nx, ny = -sy, sx
            r0, r1 = POINTER_FROM * radius, POINTER_TO * radius
            o = self.wall
            self.coords(self.part["pointer"], x0 + sx * r0, y0 + sy * r0, x0 + sx * r1, y0 + sy * r1)
            self.coords(self.part["shade"], x0 + sx * r0 - nx * o, y0 + sy * r0 - ny * o, x0 + sx * r1 - nx * o, y0 + sy * r1 - ny * o)
            self.coords(self.part["lit"], x0 + sx * r0 + nx * o, y0 + sy * r0 + ny * o, x0 + sx * r1 + nx * o, y0 + sy * r1 + ny * o)
            if "zero" in self.part:
                zr = -z.value_min / z.value_range
                za = math.radians(-KNOB_DEG / 2 + KNOB_DEG * zr)
                zx, zy = math.sin(za), -math.cos(za)
                self.coords(self.part["zero"], x0 + zx * TICK_IN * radius, y0 + zy * TICK_IN * radius,
                            x0 + zx * TICK_OUT * radius, y0 + zy * TICK_OUT * radius)

        # -- the switch

        def build_switch(self, x0, y0, radius):
            h = max(8, radius // 2)
            w = 2 * h
            cy = y0 - radius // 4
            self.pill = (x0 - w // 2, cy - h // 2, x0 + w // 2, cy + h // 2)
            track = zynthian_gui_config.color_switch_track
            self.add("cap_l", self.create_oval(0, 0, 0, 0, fill=track, width=0))
            self.add("cap_r", self.create_oval(0, 0, 0, 0, fill=track, width=0))
            self.add("body", self.create_rectangle(0, 0, 0, 0, fill=track, width=0))
            self.add("thumb", self.create_oval(0, 0, 0, 0, fill=zynthian_gui_config.color_switch_thumb, width=0))
            l, t, r, b = self.pill
            self.coords(self.part["cap_l"], l, t, l + h, b)
            self.coords(self.part["cap_r"], r - h, t, r, b)
            self.coords(self.part["body"], l + h // 2, t, r - h // 2, b)
            self.coords(self.value_text, x0, y0 + radius // 2)

        def move_switch(self, z):
            l, t, r, b = self.pill
            h, pad = b - t, 2
            on = self.value_plot >= 0.5
            x = (r - h + pad) if on else (l + pad)
            self.coords(self.part["thumb"], x, t + pad, x + h - 2 * pad, b - pad)
            colour = zynthian_gui_config.color_on if on else zynthian_gui_config.color_switch_track
            for name in ("cap_l", "cap_r", "body"):
                self.itemconfig(self.part[name], fill=colour)

        # -- the selector

        def build_selector(self, x0, y0, radius):
            n = max(1, len(self.zctrl.ticks))
            h = max(8, radius // 2)
            w = int(1.6 * radius)
            cy = y0 - radius // 4
            l, t, r, b = x0 - w // 2, cy - h // 2, x0 + w // 2, cy + h // 2
            self.strip = (l, t, r, b)
            k = h // 2
            self.add("strip", self.create_polygon(l + k, t, r - k, t, r, t + k, r - k, b, l + k, b, l, t + k,
                                                  fill=zynthian_gui_config.color_panel_hl, outline=zynthian_gui_config.color_off,
                                                  smooth=True))
            self.add("chosen", self.create_rectangle(0, 0, 0, 0, fill=zynthian_gui_config.color_on, width=0))
            self.coords(self.value_text, x0, y0 + radius // 2)

        def move_selector(self, z):
            l, t, r, b = self.strip
            n = max(1, len(z.ticks))
            seg = (r - l) / n
            i = z.get_value2index()
            self.coords(self.part["chosen"], l + seg * i, t + 2, l + seg * (i + 1), b - 2)

        # -- the display

        def build_display(self, x0, y0, radius):
            w, h = int(1.8 * radius), max(8, int(0.9 * radius))
            self.show_image("glass", glass_face(w, h, tokens()), x0 - w // 2, y0 - h // 2)
            self.coords(self.value_text, x0, y0)

        def move_display(self, z):
            pass

        # -- the selection and the pickup marker; Tk's thread

        def frame(self):
            """The selection: a frame around the controller in the colour the stock arc would take; none when unselected."""
            if self.hidden:
                return
            w, h = self.winfo_width(), self.winfo_height()
            if self.frame_item is None:
                self.frame_item = self.create_rectangle(FRAME_PX // 2, FRAME_PX // 2, w - FRAME_PX, h - FRAME_PX,
                                                        outline="", width=FRAME_PX, state=tkinter.HIDDEN)
            self.coords(self.frame_item, FRAME_PX // 2, FRAME_PX // 2, w - FRAME_PX, h - FRAME_PX)
            if self.frame_color:
                self.itemconfig(self.frame_item, outline=self.frame_color, state=tkinter.NORMAL)
            else:
                self.itemconfig(self.frame_item, state=tkinter.HIDDEN)

    return zynthian_gui_controller_tk


def _rgb(colour):
    from PIL import ImageColor
    return ImageColor.getrgb(colour)[:3]


def _hex(c):
    return "#%02x%02x%02x" % tuple(c)


def _shade(colour, _t):
    """The groove's shaded wall: the edge colour, darker."""
    return _hex(_mix(_rgb(colour), (0, 0, 0), 0.5))


def _lighter(colour):
    """The groove's lit wall."""
    return _hex(_mix(_rgb(colour), (255, 255, 255), 0.25))
