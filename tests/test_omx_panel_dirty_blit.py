# -*- coding: utf-8 -*-
#
# A drawn panel blits only what a draw changed (zynthian-ui#59): the panel's image on the screen is one Tk photo, kept,
# and a draw that changed a band of rows converts and copies only that band into it. The first draw, a new size and a
# new background blit the whole panel; a draw that changed nothing blits nothing. Whatever was blitted, the image on
# the screen equals the whole draw over the background. The renderer's own dirty rectangles (Open-Mixer/omx-panel#78)
# take the place of the compared rows when the renderer gives them.
#
# The panel view module's PanelImage, with real PIL and the Tk photo calls recorded into a PIL image that stands for
# the photo on the screen.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import unittest

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


def frame(bar_top):
    """A panel draw: a translucent box (alpha over the background) and one bar whose top is at `bar_top`."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((10, 10, 60, 100), fill=(200, 120, 40, 128))
    d.rectangle((120, bar_top, 140, 110), fill=(230, 230, 230, 255))
    return im.tobytes()


def shown(pixels, w=W, h=H, bg=BG):
    """The whole draw over the background: what the screen must show."""
    return Image.alpha_composite(Image.new("RGBA", (w, h), bg), Image.frombuffer("RGBA", (w, h), pixels, "raw", "RGBA", 0, 1))


@unittest.skipUnless(Image, "no PIL")
class DirtyBlit(unittest.TestCase):
    def setUp(self):
        if not hasattr(view, "PanelImage"):
            self.fail("the panel view has no PanelImage: every frame converts and blits the whole panel")
        test = self

        class Recorded(view.PanelImage):
            """The Tk photo as a PIL image; each blit recorded as (x, y, width, height)."""

            def _new(self, image):
                test.screen = image.copy()
                test.blits.append((0, 0) + image.size)

            def _put(self, image, x, y):
                test.screen.paste(image, (x, y))
                test.blits.append((x, y) + image.size)

        self.blits, self.screen = [], None
        self.panel = Recorded(BG)

    def test_the_first_draw_blits_the_whole_panel(self):
        self.panel.show(frame(50), W, H)
        self.assertEqual(self.blits, [(0, 0, W, H)])
        self.assertEqual(self.screen.tobytes(), shown(frame(50)).tobytes())

    def test_a_moved_bar_blits_only_its_rows(self):
        self.panel.show(frame(50), W, H)
        self.panel.show(frame(30), W, H)
        self.assertEqual(self.blits[1], (0, 30, W, 20), "the rows from the bar's new top to its old one")
        self.assertEqual(self.screen.tobytes(), shown(frame(30)).tobytes(), "the screen is the whole new draw")

    def test_an_unchanged_draw_blits_nothing(self):
        self.panel.show(frame(50), W, H)
        self.panel.show(frame(50), W, H)
        self.assertEqual(len(self.blits), 1)

    def test_a_new_size_or_background_blits_the_whole_panel(self):
        self.panel.show(frame(50), W, H)
        small = bytes(W * (H - 20) * 4)
        self.panel.show(small, W, H - 20)
        self.assertEqual(self.blits[-1], (0, 0, W, H - 20))
        self.panel.show(small, W, H - 20)
        self.panel.background = "#3a424d"
        self.panel.show(small, W, H - 20)
        self.assertEqual(self.blits[-1], (0, 0, W, H - 20))
        self.assertEqual(self.screen.tobytes(), shown(small, W, H - 20, "#3a424d").tobytes())

    def test_a_cleared_canvas_blits_the_whole_panel(self):
        self.panel.show(frame(50), W, H)
        self.panel.forget()  # the canvas was cleared under it (the strips, a rebuild)
        self.panel.show(frame(50), W, H)
        self.assertEqual(self.blits[-1], (0, 0, W, H))

    def test_the_renderers_rectangles_are_taken_when_given(self):
        self.panel.show(frame(50), W, H)
        self.panel.show(frame(30), W, H, dirty=[(120, 30, 21, 20)])
        self.assertEqual(self.blits[1], (120, 30, 21, 20))
        self.assertEqual(self.screen.tobytes(), shown(frame(30)).tobytes())


@unittest.skipUnless(Image, "no PIL")
class OnePath(unittest.TestCase):
    def test_the_widget_and_the_pi_measurement_blit_through_panel_image(self):
        """One path to the screen: the widget paints and the Pi measurement times the same PanelImage, so a figure is the
        widget's."""
        root = os.path.join(HERE, "..")
        for path in ("zyngui/zynthian_widget_omx_panel.py", "tests/pi/blit_per_frame_on_the_pi.py"):
            with self.subTest(path=path):
                with open(os.path.join(root, path)) as f:
                    source = f.read()
                self.assertTrue("PanelImage(" in source, "blits through PanelImage")
                self.assertFalse("ImageTk.PhotoImage(" in source, "builds no PhotoImage of its own")


class WidgetForgets(unittest.TestCase):
    def test_the_widget_blits_the_whole_panel_after_clearing_its_canvas(self):
        """The strips (or a rebuild) clear the canvas under the panel's photo: the next paint must blit all of it."""
        import sys
        sys.path.insert(0, HERE)
        import test_omx_panel_renderer_crash as harness
        case = harness.WidgetOverAStoppedRenderer("test_the_next_open_draws_again")
        case.setUp()
        try:
            if not hasattr(harness.FakeView.stopped, "__mro__") or not hasattr(case.w, "panel_image"):
                self.fail("the widget keeps no PanelImage")
            harness.FakeView.crash = False
            case.w.set_processor(case.proc)
            case.w.refresh_gui()
            self.assertIsNotNone(case.w.panel_image.last, "painted")
            for clear in (lambda: case.w.build_drawn(), lambda: (setattr(case.w, "drawn", None), case.w.refresh_gui())):
                case.w.set_processor(case.proc)
                case.w.refresh_gui()
                clear()
                self.assertIsNone(case.w.panel_image.last, "the next paint blits the whole panel")
        finally:
            case.doCleanups()


if __name__ == "__main__":
    unittest.main()
