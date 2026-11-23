#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian GUI (zynthian_gui_omx_panel_image)
#
# The drawn panel on the screen: a Tk photo kept on a canvas, blitted only where a draw changed (zynthian-ui#59). The
# renderer's door (zyngine/zynthian_omx_panel_view.py) gives the pixels; putting them on a Tk canvas is the UI's, so
# this lives in zyngui and zyngine stays toolkit-free (tests/architecture/test_layering.py). Standard library and PIL
# only, so the tests and tools/pi load it by path.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

# ---- The panel on the screen ----

def changed_rows(before, after, stride):
    """The band of rows two draws of one size differ in, (first, past the last); None when they are the same. A binary
    search over the rows that match from the top and from the bottom, never a Python loop over every row."""
    if before == after:
        return None
    # each step is one memcmp of `before` against a window on `after`, no copy (a memoryview slice compared with ==
    # goes item by item: a row loop over them took 7.3 ms of a 1024 x 416 frame on the Pi)
    a, b = bytes(before), memoryview(after)
    n = len(b)
    rows = n // stride
    lo, hi = 0, rows  # rows above `lo` match
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if a.startswith(b[:mid * stride]):
            lo = mid
        else:
            hi = mid - 1
    top = lo
    lo, hi = 0, rows - top  # rows below the band that match from the bottom (a suffix holding row `top` never does)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if a.endswith(b[n - mid * stride:]):
            lo = mid
        else:
            hi = mid - 1
    return top, rows - lo


class PanelImage:
    """The panel on the screen: one Tk photo on a canvas, kept (zynthian-ui#59). show() blits only what a draw changed:
    the renderer's own rectangles when it gives them, else the band of rows that differ from the draw before. The first
    draw, a new size, a new background and a cleared canvas (forget) blit the whole panel; an unchanged draw blits
    nothing. Each blit is the draw over the background, so the screen always equals the whole draw over it."""

    def __init__(self, background, canvas=None):
        self.background = background
        self.canvas = canvas
        self.photo = None
        self.last = None  # (pixels, width, height, background) of the draw on the screen

    def forget(self):
        """The canvas was cleared under the panel: the next show blits the whole of it."""
        self.last = None

    def show(self, pixels, width, height, dirty=None):
        """Put a draw (RGBA, straight alpha, rows of width * 4 bytes) on the screen; the boxes blitted, (x, y, w, h)."""
        from PIL import Image
        stride = width * 4
        full = self.last is None or self.last[1:] != (width, height, self.background)
        if full:
            boxes = [(0, 0, width, height)]
        elif dirty is not None:
            boxes = [tuple(int(v) for v in d) for d in dirty if d[2] > 0 and d[3] > 0]
        else:
            band = changed_rows(self.last[0], pixels, stride)
            boxes = [] if band is None else [(0, band[0], width, band[1] - band[0])]
        self.last = (pixels, width, height, self.background)
        for x, y, w, h in boxes:
            rows = Image.frombuffer("RGBA", (width, h), pixels[y * stride:(y + h) * stride], "raw", "RGBA", 0, 1)
            region = rows if w == width else rows.crop((x, 0, x + w, h))
            image = Image.alpha_composite(Image.new("RGBA", (w, h), self.background), region)
            if full:
                self._new(image)
            else:
                self._put(image, x, y)
        return boxes

    def _new(self, image):
        """The whole panel: a new photo, the canvas's only item."""
        from PIL import ImageTk
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

    def _put(self, image, x, y):
        """A region: converted alone and copied into the photo on the screen, which Tk redraws where it changed."""
        from PIL import ImageTk
        region = ImageTk.PhotoImage(image)
        self.canvas.tk.call(str(self.photo), "copy", str(region), "-to", x, y)
