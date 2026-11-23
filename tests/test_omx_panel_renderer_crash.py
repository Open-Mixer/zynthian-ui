# -*- coding: utf-8 -*-
#
# A crash in omx-panel's renderer leaves the UI running (zynthian-ui#44). The panel view loads
# libomx-panel-render.so.0 with ctypes; a fault inside it (a null pointer in omx_panel_view_draw) must stop the renderer,
# never the UI's process. The panel says the renderer stopped and is drawn as strips; the next open draws again.
#
# The crash: a stub renderer, built here from C, with every function the view declares and an omx_panel_view_draw that
# faults (SIGSEGV). A Python process that stands for the UI opens a view on it and draws, then opens one on the real
# library (the one $ZYNTHIAN_OMX_PANEL_RENDER names, as CI builds it; that row is skipped where there is none). The
# widget: zyngui/zynthian_widget_omx_panel.py's own build and refresh, over a view that says the renderer stopped;
# tkinter, PIL, the base widget, the gestures and the touch layer are stand-ins.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from tests.omx_panel_widget_stub import load_widget  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VIEW = os.path.join(ROOT, "zyngine", "zynthian_omx_panel_view.py")
WIDGET = os.path.join(ROOT, "zyngui", "zynthian_widget_omx_panel.py")
LAYOUT = os.path.join(HERE, "fixtures", "omx_panel", "omx-eq8.json")

STUB = r"""
#include <signal.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
static int view;
void *omx_panel_view_create_from_files(const char *l, const char *t, char *e, size_t n) { return &view; }
void omx_panel_view_destroy(void *v) {}
uint32_t omx_panel_view_count(void *v) { return 0; }
const char *omx_panel_view_symbol(void *v, uint32_t i) { return ""; }
void omx_panel_view_set_title(void *v, const char *b, const char *n) {}
bool omx_panel_view_set_value(void *v, uint32_t i, double f, const char *t) { return true; }
bool omx_panel_view_set_choice(void *v, uint32_t i, uint32_t a, uint32_t c, const char *t) { return true; }
bool omx_panel_view_set_meter(void *v, uint32_t i, double x, double e) { return true; }
bool omx_panel_view_set_curve(void *v, uint32_t d, const double *x, const double *y, uint32_t n) { return true; }
void omx_panel_view_natural_size(void *v, uint32_t *w, uint32_t *h) { *w = 64; *h = 32; }
bool omx_panel_view_draw(void *v, void *buffer) { raise(SIGSEGV); return false; }  /* a fault inside the renderer */
bool omx_panel_view_set_surface(void *v, uint32_t w, uint32_t h, double s) { return true; }
bool omx_panel_view_set_travel(void *v, uint32_t i, const void *t) { return true; }
size_t omx_panel_view_input(void *v, const void *e, void *c, size_t n, void *a) { return 0; }
bool omx_panel_view_target_rect(void *v, uint32_t i, double *r, double *t) { return false; }
size_t omx_panel_view_tick(void *v, double t, void *c, size_t n, void *a) { return 0; }
const char *omx_panel_word_name(int w) { return ""; }
"""

# The UI's part: open a view on the crashing renderer and draw, then a view on the real one
UI = r"""
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("panel_view", sys.argv[1])
view = importlib.util.module_from_spec(spec)
spec.loader.exec_module(view)
layout = json.load(open(sys.argv[2]))["layout"]
os.environ["ZYNTHIAN_OMX_PANEL_RENDER"] = sys.argv[3]
v = view.View(layout)
v.set_surface(64, 32)
try:
    v.draw(64, 32)
    print("drew", flush=True)
except view.RendererStopped as e:
    print("stopped:", e, flush=True)
if sys.argv[4]:
    os.environ["ZYNTHIAN_OMX_PANEL_RENDER"] = sys.argv[4]
    again = view.View(layout)
    again.set_surface(64, 32)
    print("again:", len(again.draw(64, 32)), flush=True)
print("ui alive", flush=True)
"""


def real_renderer():
    """The real library: what $ZYNTHIAN_OMX_PANEL_RENDER names (CI's build), when it is a file."""
    name = os.environ.get("ZYNTHIAN_OMX_PANEL_RENDER", "")
    return name if os.path.isfile(name) else ""


class RendererCrash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which("cc") or shutil.which("gcc")
        if not cc:
            raise unittest.SkipTest("no C compiler to build the crashing renderer")
        cls.dir = tempfile.mkdtemp()
        src = os.path.join(cls.dir, "stub.c")
        with open(src, "w") as f:
            f.write(STUB)
        cls.stub = os.path.join(cls.dir, "libomx-panel-render-crash.so")
        subprocess.run([cc, "-shared", "-fPIC", "-o", cls.stub, src], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def ui(self, real=""):
        return subprocess.run([sys.executable, "-c", UI, VIEW, LAYOUT, self.stub, real], capture_output=True, text=True,
                              timeout=60)

    def test_a_fault_in_the_renderer_leaves_the_ui_running(self):
        r = self.ui()
        self.assertEqual(r.returncode, 0, f"the UI's process died: {r.returncode}\n{r.stdout}{r.stderr}")
        self.assertIn("ui alive", r.stdout)

    def test_the_view_says_the_renderer_stopped_and_how(self):
        r = self.ui()
        self.assertRegex(r.stdout, r"stopped: .*renderer.*stopped.*SIGSEGV", r.stdout + r.stderr)

    def test_the_next_open_draws_again(self):
        real = real_renderer()
        if not real:
            self.skipTest("no real renderer: $ZYNTHIAN_OMX_PANEL_RENDER names no file (CI builds one)")
        r = self.ui(real)
        self.assertIn(f"again: {64 * 32 * 4}", r.stdout, r.stdout + r.stderr)


# ---- The widget over a renderer that stopped ----

class FakeView:
    """A view whose renderer stops at the first draw while `crash` is set."""
    opened = 0
    crash = True

    def __init__(self, layout, tools_dir=None, look=None):
        FakeView.opened += 1
        self.symbols, self.meters, self.drew = [], [], 0

    def set_title(self, *a):
        pass

    def set_surface(self, *a):
        pass

    def close(self):
        pass

    def draw(self, w, h):
        if FakeView.crash:
            raise self.stopped("omx-panel's renderer stopped (SIGSEGV)")
        self.drew += 1
        return bytes(w * h * 4)


class WidgetOverAStoppedRenderer(unittest.TestCase):
    def setUp(self):
        module, panel_view, self.modules = load_widget()
        if not hasattr(panel_view, "RendererStopped"):
            self.fail("the panel view has no RendererStopped to say the renderer stopped")
        FakeView.stopped, FakeView.opened, FakeView.crash = panel_view.RendererStopped, 0, True
        self.patch = mock.patch.dict(sys.modules, self.modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        mock.patch.object(panel_view, "View", FakeView).start()
        mock.patch.object(panel_view, "screen_part", lambda layout, keys: (layout, {})).start()
        self.addCleanup(mock.patch.stopall)
        w = module.zynthian_widget_omx_panel(None)
        w.width, w.height = 120, 60
        w.zyngui_control = types.SimpleNamespace(zcontrollers=[], show_menu=lambda: None)
        engine = types.SimpleNamespace(drawn=({"controls": []},), name="omx eq8", zctrls={}, curve=lambda d: [],
                                       meter=lambda s: None)
        self.proc = types.SimpleNamespace(engine=engine)
        w.set_processor(self.proc)
        self.w = w

    def said(self):
        return " ".join(str(c.kwargs.get("text", "")) for c in self.w.widget_canvas.create_text.call_args_list)

    def test_the_ui_goes_on_and_the_panel_says_the_renderer_stopped(self):
        self.w.refresh_gui()  # draws: the renderer stops
        self.assertIsNone(self.w.drawn, "the stopped view is dropped")
        self.w.refresh_gui()
        self.assertIn("renderer stopped", self.said())

    def test_no_reopen_until_the_panel_is_opened_again(self):
        self.w.refresh_gui()
        opened = FakeView.opened
        for _ in range(3):
            self.w.build()
            self.w.refresh_gui()
        self.assertEqual(FakeView.opened, opened, "a stopped renderer is not started again on every refresh")

    def test_the_next_open_draws_again(self):
        self.w.refresh_gui()
        FakeView.crash = False
        self.w.set_processor(self.proc)
        self.w.refresh_gui()
        self.assertIsNotNone(self.w.drawn)
        self.assertEqual(self.w.drawn.drew, 1)


if __name__ == "__main__":
    unittest.main()
