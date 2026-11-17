# -*- coding: utf-8 -*-
#
# The panel view draws through the renderer's dirty entry when the renderer has one (zynthian-ui#59, the consumer of
# Open-Mixer/omx-panel#78's omx_panel_view_draw_dirty): the view keeps ONE buffer between draws, the one the last draw went
# into, so the renderer repaints only the cells that changed and says where; a draw answers (pixels, rects), the pixels
# byte-equal to a full draw of the same state, and the rects go to PanelImage, which blits only them. The first draw is
# the whole panel as one rect. A renderer without the entry (a release before it) draws the whole panel and answers no
# rects, and PanelImage falls back to the band of changed rows: the full draw is then the only path, as before.
#
# Real PIL draws the frames a fake renderer answers with; the fake has the entry as omx-panel declares it (a buffer that
# does not hold its last draw gets the whole panel), so a view that allocates a new buffer per draw can never get a cell.
# The renderer's own process is exercised too: _serve in a thread of this process, the UI's shared memory the one buffer.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ctypes
import importlib.util
import os
import socket
import threading
import unittest
from multiprocessing import connection
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("omx_panel_view", os.path.join(HERE, "..", "zyngine", "zynthian_omx_panel_view.py"))
view = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(view)

try:
    from PIL import Image, ImageDraw
except ImportError:  # the Pi has PIL, CI installs it
    Image = None

W, H = 200, 120
BG = "#0b0e11"
CELL = (120, 20, 21, 91)  # the bar's cell: every pixel its reading can move
LAYOUT = {"controls": [{"symbol": "gain", "kind": "bar"}]}


def frame(width, height, value):
    """A panel draw: a translucent box, and one bar whose top follows `value` (1.0 at the top of its cell)."""
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((10, 10, 60, 100), fill=(200, 120, 40, 128))
    top = CELL[1] + int(round((1.0 - value) * (CELL[3] - 11)))
    d.rectangle((CELL[0], top, CELL[0] + CELL[2] - 1, CELL[1] + CELL[3] - 1), fill=(230, 230, 230, 255))
    return im.tobytes()


def shown(pixels, w=W, h=H, bg=BG):
    """The whole draw over the background: what the screen must show."""
    return Image.alpha_composite(Image.new("RGBA", (w, h), bg), Image.frombuffer("RGBA", (w, h), pixels, "raw", "RGBA", 0, 1))


class FakeRenderer:
    """omx-panel's renderer as the view module's ctypes door sees it, without the dirty entry: every draw is the whole
    panel. Each draw's buffer address is recorded."""

    def __init__(self):
        self.value = 0.5
        self.addresses = []

    def omx_panel_view_create_from_files(self, path, tools, err, cap):
        return 1

    def omx_panel_view_destroy(self, v):
        pass

    def omx_panel_view_count(self, v):
        return 1

    def omx_panel_view_symbol(self, v, i):
        return b"gain"

    def omx_panel_view_set_value(self, v, index, fraction, text):
        self.value = fraction
        return True

    def omx_panel_view_draw(self, v, bufp):
        buf = bufp._obj
        self.addresses.append(buf.pixels)
        pixels = frame(buf.width, buf.height, self.value)
        ctypes.memmove(buf.pixels, pixels, len(pixels))
        return True


class FakeDirtyRenderer(FakeRenderer):
    """With omx_panel_view_draw_dirty as omx-panel#78 declares it: the buffer the last draw went into, still holding it,
    gets the bar's cell repainted and reported when the reading moved (nothing, when it did not); the first draw and any
    other buffer get the whole panel, drawn and reported as one rect."""

    def __init__(self):
        super().__init__()
        self.last = None  # (address, width, height, scale, value) of the last draw

    def omx_panel_view_draw_dirty(self, v, bufp, rects, cap, countp):
        buf = bufp._obj
        self.addresses.append(buf.pixels)
        key = (buf.pixels, buf.width, buf.height, buf.scale)
        pixels = frame(buf.width, buf.height, self.value)
        if self.last is None or self.last[:4] != key:
            ctypes.memmove(buf.pixels, pixels, len(pixels))
            boxes = [(0, 0, buf.width, buf.height)]
        elif self.last[4] != self.value:
            x, y, w, h = CELL
            stride = buf.width * 4
            for row in range(y, y + h):
                at = row * stride + x * 4
                ctypes.memmove(buf.pixels + at, pixels[at:at + w * 4], w * 4)
            boxes = [CELL]
        else:
            boxes = []
        for i, (x, y, w, h) in enumerate(boxes):
            rects[i].x, rects[i].y, rects[i].width, rects[i].height = x, y, w, h
        countp._obj.value = len(boxes)
        self.last = key + (self.value,)
        return True


class ThreadHost(view._Host):
    """The renderer's process as a thread of this one: _serve over a socketpair, so the fake renderer is the library it
    loads and this test reads what it recorded."""

    class _Process:
        def poll(self):
            return None

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    def __init__(self):
        ours, theirs = socket.socketpair()
        self.process = self._Process()
        self.conn = connection.Connection(ours.detach())
        self.stopped = None
        threading.Thread(target=view._serve, args=(theirs.detach(),), daemon=True).start()


class Recorder:
    """A PanelImage with the Tk photo as a PIL image; each blit recorded as (x, y, width, height)."""

    def __init__(self):
        self.blits, self.screen = [], None
        test = self

        class Recorded(view.PanelImage):
            def _new(self, image):
                test.screen = image.copy()
                test.blits.append((0, 0) + image.size)

            def _put(self, image, x, y):
                test.screen.paste(image, (x, y))
                test.blits.append((x, y) + image.size)

        self.panel = Recorded(BG)

    def show(self, drawn):
        pixels, rects = drawn
        return self.panel.show(pixels, W, H, rects)


@unittest.skipUnless(Image, "no PIL")
class DirtyDraw(unittest.TestCase):
    """The view in the renderer's own process (_LibraryView), over a renderer with the dirty entry."""

    def setUp(self):
        self.lib = FakeDirtyRenderer()
        self.enterContext(mock.patch.object(view, "library", return_value=self.lib))
        self.view = view._LibraryView(LAYOUT)

    def test_the_first_draw_is_the_whole_panel_as_one_rect(self):
        pixels, rects = self.view.draw(W, H)
        self.assertEqual(rects, [(0, 0, W, H)])
        self.assertEqual(pixels, frame(W, H, 0.5))

    def test_one_knob_change_draws_its_cell_and_the_pixels_equal_a_full_draw(self):
        self.view.draw(W, H)
        self.view.set_value(0, 0.75, "")
        pixels, rects = self.view.draw(W, H)
        self.assertEqual(rects, [CELL], "the cell that moved, nothing else")
        self.assertEqual(pixels, frame(W, H, 0.75), "byte-equal to a full draw of the same state")

    def test_the_view_keeps_one_buffer_between_draws(self):
        for value in (0.5, 0.75, 0.25):
            self.view.set_value(0, value, "")
            self.view.draw(W, H)
        self.assertEqual(len(set(self.lib.addresses)), 1, "the buffer the last draw went into, every draw")

    def test_an_unchanged_draw_reports_no_rect(self):
        self.view.draw(W, H)
        pixels, rects = self.view.draw(W, H)
        self.assertEqual(rects, [])
        self.assertEqual(pixels, frame(W, H, 0.5))

    def test_a_new_size_is_a_whole_draw(self):
        self.view.draw(W, H)
        pixels, rects = self.view.draw(W, H - 20)
        self.assertEqual(rects, [(0, 0, W, H - 20)])
        self.assertEqual(pixels, frame(W, H - 20, 0.5))

    def test_the_cell_is_what_the_screen_blits(self):
        r = Recorder()
        r.show(self.view.draw(W, H))
        self.view.set_value(0, 0.75, "")
        r.show(self.view.draw(W, H))
        self.assertEqual(r.blits, [(0, 0, W, H), CELL], "the whole panel first, then only the cell")
        self.assertEqual(r.screen.tobytes(), shown(frame(W, H, 0.75)).tobytes(), "the screen is the whole new draw")
        r.show(self.view.draw(W, H))
        self.assertEqual(len(r.blits), 2, "an unchanged draw blits nothing")


@unittest.skipUnless(Image, "no PIL")
class WithoutTheEntry(unittest.TestCase):
    """A renderer released before omx-panel#78: the full draw is the only path, and the screen compares rows."""

    def setUp(self):
        self.lib = FakeRenderer()
        self.enterContext(mock.patch.object(view, "library", return_value=self.lib))
        self.view = view._LibraryView(LAYOUT)

    def test_every_draw_is_whole_and_answers_no_rects(self):
        pixels, rects = self.view.draw(W, H)
        self.assertIsNone(rects)
        self.assertEqual(pixels, frame(W, H, 0.5))
        self.view.set_value(0, 0.75, "")
        pixels, rects = self.view.draw(W, H)
        self.assertIsNone(rects)
        self.assertEqual(pixels, frame(W, H, 0.75))

    def test_the_screen_blits_the_band_of_changed_rows(self):
        r = Recorder()
        r.show(self.view.draw(W, H))
        self.view.set_value(0, 0.75, "")
        r.show(self.view.draw(W, H))
        x, y, w, h = r.blits[1]
        self.assertEqual((x, w), (0, W), "a band of rows")
        self.assertTrue(CELL[1] <= y and y + h <= CELL[1] + CELL[3], "inside the bar's cell")
        self.assertEqual(r.screen.tobytes(), shown(frame(W, H, 0.75)).tobytes())


@unittest.skipUnless(Image, "no PIL")
class InTheRenderersProcess(unittest.TestCase):
    """The UI's View: the renderer's process draws into the UI's shared memory, the one buffer kept between draws."""

    def setUp(self):
        self.lib = FakeDirtyRenderer()
        self.enterContext(mock.patch.object(view, "library", return_value=self.lib))
        self.enterContext(mock.patch.object(view, "_Host", ThreadHost))
        self.enterContext(mock.patch.object(view, "_the_host", None))
        self.view = view.View(LAYOUT)
        self.addCleanup(self.view.close)

    def test_the_shared_memory_is_the_buffer_the_renderer_repaints(self):
        r = Recorder()
        r.show(self.view.draw(W, H))
        self.view.set_value(0, 0.75, "")
        pixels, rects = self.view.draw(W, H)
        r.show((pixels, rects))
        self.assertEqual(rects, [CELL])
        self.assertEqual(pixels, frame(W, H, 0.75))
        self.assertEqual(len(set(self.lib.addresses)), 1, "one buffer between draws: the shared memory")
        self.assertEqual(r.blits, [(0, 0, W, H), CELL])
        self.assertEqual(r.screen.tobytes(), shown(frame(W, H, 0.75)).tobytes())


if __name__ == "__main__":
    unittest.main()
