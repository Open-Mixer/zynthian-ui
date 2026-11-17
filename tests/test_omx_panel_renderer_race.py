# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Pau Aliagas
#
# A page change while the plot task draws leaves omx-panel's renderer running and the look on the screen
# (zynthian-ui#79). The UI talks to the renderer's process over one connection, from two threads: the plot task (Tk's
# thread, every 32 ms) and whatever changes the page (the CUIA thread). On the Pi a walk of omx-eq8's pages mixed their
# requests and answers: one thread unpickled the middle of the other's answer (`invalid load key, '\x00'`), the other
# read an empty message, took the renderer as stopped and killed it (SIGKILL), and every controller was drawn stock for
# the rest of the session.
#
# Three things are held here, each over the real files:
# - the connection: two threads driving zyngine/zynthian_omx_panel_view.py's own View over a real renderer process
#   (`--serve`, as the UI starts it), each taking its own answer, the renderer still running. The library the process
#   loads is a stub built here from C (the race is in the client, not in what the library draws);
# - the owner: the drawn controller and the panel widget give the renderer's calls to Tk's thread when a page change
#   reaches them from another one, so a view is never closed under a draw;
# - the look after a stop: the renderer is started again for the next page, the controllers are drawn in the look
#   again, and a renderer that stops every time is given up after STOPS_IN_A_ROW starts, said by name.

import importlib.util
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import types
import unittest
from unittest import mock

from tests import test_ui_look_widgets as look_widgets
from tests.omx_panel_widget_stub import load_widget

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VIEW = os.path.join(ROOT, "zyngine", "zynthian_omx_panel_view.py")
LAYOUT = os.path.join(HERE, "fixtures", "omx_panel", "omx-eq8.json")
W, H = 64, 32

# Every function the view declares. Built plain it draws nothing and answers; built with -DFAULT its draw faults.
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
#ifdef FAULT
bool omx_panel_view_draw(void *v, void *buffer) { raise(SIGSEGV); return false; }
#else
bool omx_panel_view_draw(void *v, void *buffer) { return true; }
#endif
bool omx_panel_view_set_surface(void *v, uint32_t w, uint32_t h, double s) { return true; }
bool omx_panel_view_set_travel(void *v, uint32_t i, const void *t) { return true; }
size_t omx_panel_view_input(void *v, const void *e, void *c, size_t n, void *a) { return 0; }
bool omx_panel_view_target_rect(void *v, uint32_t i, double *r, double *t) { return false; }
size_t omx_panel_view_tick(void *v, double t, void *c, size_t n, void *a) { return 0; }
const char *omx_panel_word_name(int w) { return ""; }
"""


def load_view():
    """The panel view module, a copy of its own: its renderer process is this test's."""
    spec = importlib.util.spec_from_file_location("panel_view_race", VIEW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubRenderer(unittest.TestCase):
    """The two stub libraries, and a view module whose renderer process is ended with the test."""

    @classmethod
    def setUpClass(cls):
        cc = shutil.which("cc") or shutil.which("gcc")
        if not cc:
            raise unittest.SkipTest("no C compiler to build the stub renderer")
        cls.dir = tempfile.mkdtemp()
        src = os.path.join(cls.dir, "stub.c")
        with open(src, "w") as f:
            f.write(STUB)
        cls.quiet = os.path.join(cls.dir, "libomx-panel-render-quiet.so")
        cls.faulting = os.path.join(cls.dir, "libomx-panel-render-fault.so")
        subprocess.run([cc, "-shared", "-fPIC", "-o", cls.quiet, src], check=True)
        subprocess.run([cc, "-shared", "-fPIC", "-DFAULT", "-o", cls.faulting, src], check=True)
        with open(LAYOUT) as f:
            cls.layout = json.load(f)["layout"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        self.view = load_view()
        self.addCleanup(self.end)
        self.library(self.quiet)

    def library(self, path):
        """The library the next renderer process loads."""
        patch = mock.patch.dict(os.environ, {"ZYNTHIAN_OMX_PANEL_RENDER": path})
        patch.start()
        self.addCleanup(patch.stop)

    def end(self):
        host = self.view._the_host
        if host is not None and host.process.poll() is None:
            host.process.kill()
            host.process.wait()


class TwoThreadsOneRenderer(StubRenderer):
    PAGES = 300  # page changes; the plot thread draws until the last one

    def test_a_page_change_while_the_plot_task_draws_leaves_each_its_own_answer_and_the_renderer_running(self):
        view = self.view
        plotted = view.View(self.layout)
        plotted.set_surface(W, H)
        said, done = [], threading.Event()

        def plot():  # the plot task: the page's panel, drawn again and again
            try:
                while not done.is_set():
                    n = len(plotted.draw(W, H))
                    if n != W * H * 4:
                        said.append(f"plot: a draw answered {n} bytes")
                        return
            except Exception as e:
                said.append(f"plot: {type(e).__name__}: {e}")

        def page():  # the page change: a controller's view opened, sized, measured and closed
            try:
                for _ in range(self.PAGES):
                    v = view.View(self.layout)
                    v.set_surface(W, H)
                    size = v.natural_size()
                    if size != (64, 32):
                        said.append(f"page: natural_size answered {size!r}")
                        return
                    v.close()
            except Exception as e:
                said.append(f"page: {type(e).__name__}: {e}")
            finally:
                done.set()

        logged = []
        handler = logging.Handler(logging.ERROR)
        handler.emit = lambda record: logged.append(record.getMessage())
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        threads = [threading.Thread(target=f, daemon=True) for f in (plot, page)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        hung = [t.name for t in threads if t.is_alive()]
        done.set()
        self.assertEqual(said + logged, [], "the two threads' requests and answers were mixed")
        self.assertEqual(hung, [], "a thread never got its answer")
        self.assertTrue(view._the_host.alive(), view._the_host.stopped)


class TheRendererIsStartedAgain(StubRenderer):
    def stop_one(self):
        """A view on the faulting library, drawn: the renderer stops. The process that was started for it, or None."""
        self.library(self.faulting)
        try:
            v = self.view.View(self.layout)
        except self.view.RendererStopped:
            return None
        process = v.host.process
        with self.assertLogs(level="ERROR"), self.assertRaises(self.view.RendererStopped):
            v.draw(W, H)
        return process

    def draw_one(self):
        """A view on the quiet library, drawn. Its process is ended after, so the next view starts one that loads the
        library it is given (a process loads its library once)."""
        self.library(self.quiet)
        v = self.view.View(self.layout)
        self.assertEqual(len(v.draw(W, H)), W * H * 4)
        self.assertIsNone(v.host.process.poll(), "the renderer drew and is running")
        self.end()

    def test_a_renderer_that_stops_every_time_is_given_up_and_said_by_name(self):
        limit = getattr(self.view, "STOPS_IN_A_ROW", None)
        self.assertIsNotNone(limit, "the panel view names no limit of stops in a row (STOPS_IN_A_ROW)")
        started = [self.stop_one() for _ in range(limit + 3)]
        self.assertEqual([p is not None for p in started], [True] * limit + [False] * 3,
                         f"a renderer that stops at every draw is started {limit} times, then no more")
        with self.assertRaisesRegex(self.view.RendererStopped, f"{limit} times in a row"):
            self.view.View(self.layout)

    def test_a_draw_between_two_stops_starts_the_count_again(self):
        limit = getattr(self.view, "STOPS_IN_A_ROW", None)
        self.assertIsNotNone(limit, "the panel view names no limit of stops in a row (STOPS_IN_A_ROW)")
        for _ in range(3):
            for _ in range(limit - 1):
                self.assertIsNotNone(self.stop_one())
            self.draw_one()


# ---- The drawn controller: the look after a stop, and whose thread calls the renderer

class Idle:
    """Tk's after_idle as the widgets use it: what was given to Tk's thread, run when the test says."""

    def __init__(self):
        self.due = []

    def after_idle(self, func, *args):
        self.due.append((func, args))

    def run(self):
        while self.due:
            func, args = self.due.pop(0)
            func(*args)


class ControllerHarness(unittest.TestCase):
    def setUp(self):
        if look_widgets.Image is None:
            self.skipTest("no PIL")
        with open(look_widgets.LOOK_BASE) as f:
            self.tools = look_widgets.tools_dir_with(json.load(f))
        self.addCleanup(shutil.rmtree, self.tools, True)
        cls, self.config, modules = look_widgets.load_controller(look_widgets.VINTAGE, tools_dir=self.tools)
        self.panel_view = modules["zyngine.zynthian_omx_panel_view"]
        self.idle = idle = Idle()

        class Recorded(cls):
            def photo_of(self, image):
                return ("photo", image.size)

            def after_idle(self, func, *args):
                idle.after_idle(func, *args)

        self.Recorded = Recorded

    def controller(self, zctrl, w=120, h=100):
        ctrl = self.Recorded(0, None, zctrl)
        ctrl._w, ctrl._h = w, h
        ctrl.on_size(None)
        return ctrl

    def stop_under(self, ctrl):
        """The renderer stops at the controller's next draw: the stock items come back."""
        look_widgets.FakeView.stop_at_draw = True
        ctrl.zctrl.value = 0.75
        ctrl.calculate_plot_values()
        with self.assertLogs(level="WARNING"):
            ctrl.plot_value()
        look_widgets.FakeView.stop_at_draw = False
        self.assertEqual(ctrl.of("image"), [])

    def page(self, ctrl, zctrl):
        """A page change as zynthian_gui_control.set_zcontroller makes it."""
        ctrl.config(zctrl)
        ctrl.show()


class TheLookAfterAStop(ControllerHarness):
    def test_the_next_page_is_drawn_in_the_look_again(self):
        ctrl = self.controller(look_widgets.Zctrl())
        self.stop_under(ctrl)
        opened = len(look_widgets.FakeView.opened)
        self.page(ctrl, look_widgets.Zctrl(symbol="gain", short_name="Gain"))
        self.assertEqual(len(look_widgets.FakeView.opened), opened + 1, "the next page opens a view again")
        self.assertEqual(look_widgets.FakeView.opened[-1].symbols, ["gain"])
        self.assertEqual(len(ctrl.of("image")), 1, "the renderer's face is on the canvas again")
        self.assertEqual(ctrl.items[ctrl.graph]["state"], "hidden", "the stock arc is hidden again")
        self.assertEqual(ctrl.items[ctrl.value_text]["state"], "hidden")

    def test_the_page_the_renderer_stopped_on_stays_stock_until_the_page_changes(self):
        ctrl = self.controller(look_widgets.Zctrl())
        self.stop_under(ctrl)
        opened = len(look_widgets.FakeView.opened)
        for value in (0.1, 0.2, 0.3):  # the plot task, every 32 ms
            ctrl.zctrl.value = value
            ctrl.calculate_plot_values()
            ctrl.plot_value()
        self.assertEqual(len(look_widgets.FakeView.opened), opened, "no view is opened by the plot task")
        self.assertEqual(ctrl.of("image"), [])

    def test_a_renderer_that_is_not_installed_stays_stock_on_the_next_page(self):
        absent = self.panel_view.RendererAbsent("omx-panel's renderer (libomx-panel-render.so.0) is not installed")
        look_widgets.FakeView.refuse = absent
        with self.assertLogs(level="WARNING"):
            ctrl = self.controller(look_widgets.Zctrl())
        look_widgets.FakeView.refuse = None
        opened = len(look_widgets.FakeView.opened)
        self.page(ctrl, look_widgets.Zctrl(symbol="gain", short_name="Gain"))
        self.assertEqual(len(look_widgets.FakeView.opened), opened, "an absent renderer is not asked again")
        self.assertEqual(ctrl.items[ctrl.graph]["state"], "normal")


def recording_threads(base, calls):
    """<base>, a stand-in view, noting the thread of every call the renderer would take."""

    class Noting(base):
        def __init__(self, *a, **kw):
            calls.append(("open", threading.current_thread()))
            super().__init__(*a, **kw)

    def noted(name):
        inner = getattr(base, name)

        def call(self, *a, **kw):
            calls.append((name, threading.current_thread()))
            return inner(self, *a, **kw)
        return call

    for name in ("set_title", "set_surface", "set_value", "set_choice", "set_travel", "target_rect", "draw", "close"):
        if hasattr(base, name):
            setattr(Noting, name, noted(name))
    return Noting


def in_another_thread(func):
    said = []

    def run():
        try:
            func()
        except Exception as e:
            said.append(e)

    t = threading.Thread(target=run)
    t.start()
    t.join(30)
    return said


class TheRendererIsTksThreads(ControllerHarness):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.panel_view.View = recording_threads(look_widgets.FakeView, self.calls)

    def others(self):
        return [name for name, thread in self.calls if thread is not threading.main_thread()]

    def test_a_page_change_from_another_thread_is_drawn_by_tks_thread(self):
        ctrl = self.controller(look_widgets.Zctrl())
        del self.calls[:]
        said = in_another_thread(lambda: self.page(ctrl, look_widgets.Zctrl(symbol="gain", short_name="Gain")))
        self.assertEqual(said, [])
        self.assertEqual(self.others(), [], "the page change's thread called the renderer itself")
        self.assertEqual(len(self.idle.due), 1, "one draw is given to Tk's thread, however many times the page change asks")
        self.idle.run()
        self.assertEqual(look_widgets.FakeView.opened[-1].symbols, ["gain"])
        self.assertEqual(len(look_widgets.FakeView.opened[-1].draws), 1)
        self.assertEqual(len(ctrl.of("image")), 1)

    def test_the_pickup_marker_from_another_thread_is_placed_by_tks_thread(self):
        ctrl = self.controller(look_widgets.Zctrl())
        del self.calls[:]
        said = in_another_thread(lambda: ctrl.zynpot_abs(0.9))
        self.assertEqual(said, [])
        self.assertEqual(self.others(), [], "the encoder's thread called the renderer itself")
        self.idle.run()
        self.assertIn("target_rect", [name for name, _ in self.calls])

    def test_a_blank_slot_from_another_thread_is_cleared_by_tks_thread(self):
        ctrl = self.controller(look_widgets.Zctrl())
        del self.calls[:]
        said = in_another_thread(lambda: self.page(ctrl, None))
        self.assertEqual(said, [])
        self.assertEqual(self.others(), [], "the page change's thread closed the view itself")
        self.idle.run()
        self.assertEqual(ctrl.of("image"), [])
        self.assertIn("close", [name for name, _ in self.calls])


# ---- The panel widget: its view is built by Tk's thread

class PanelView:
    """The renderer's view as the panel widget uses it."""

    def __init__(self, layout, tools_dir=None, look=None):
        self.symbols, self.meters, self.drew = [], [], 0

    def set_title(self, *a):
        pass

    def set_surface(self, *a):
        pass

    def close(self):
        pass

    def draw(self, w, h):
        self.drew += 1
        return bytes(w * h * 4)


class ThePanelIsBuiltByTksThread(unittest.TestCase):
    def setUp(self):
        module, panel_view, modules = load_widget()
        patch = mock.patch.dict("sys.modules", modules)
        patch.start()
        self.addCleanup(patch.stop)
        self.calls = []
        mock.patch.object(panel_view, "View", recording_threads(PanelView, self.calls)).start()
        mock.patch.object(panel_view, "screen_part", lambda layout, keys: (layout, {})).start()
        self.addCleanup(mock.patch.stopall)
        self.idle = Idle()
        w = module.zynthian_widget_omx_panel(None)
        w.after_idle = self.idle.after_idle
        w.width, w.height = 120, 60
        w.zyngui_control = types.SimpleNamespace(zcontrollers=[], show_menu=lambda: None)
        self.w = w

    def processor(self):
        engine = types.SimpleNamespace(drawn=({"controls": []},), name="omx eq8", zctrls={}, curve=lambda d: [],
                                       meter=lambda s: None)
        return types.SimpleNamespace(engine=engine)

    def others(self):
        return [name for name, thread in self.calls if thread is not threading.main_thread()]

    def test_a_processor_set_from_another_thread_is_built_by_tks_thread(self):
        self.w.set_processor(self.processor())
        first = self.w.drawn
        self.assertIsNotNone(first)
        del self.calls[:]
        other = self.processor()
        said = in_another_thread(lambda: self.w.set_processor(other))
        self.assertEqual(said, [])
        self.assertEqual(self.others(), [], "the page change's thread opened or closed the panel's view itself")
        self.assertIs(self.w.drawn, first, "the view is not replaced under Tk's thread")
        self.idle.run()
        self.assertIsNot(self.w.drawn, first, "Tk's thread built the panel for the processor")
        self.assertEqual([name for name, _ in self.calls].count("open"), 1)

    def test_a_refresh_before_the_build_builds_first_and_the_build_is_not_done_twice(self):
        self.w.set_processor(self.processor())
        first = self.w.drawn
        del self.calls[:]
        self.assertEqual(in_another_thread(lambda: self.w.set_processor(self.processor())), [])
        self.w.refresh_gui()  # the plot task comes before Tk is idle
        self.assertIsNot(self.w.drawn, first, "the refresh draws the processor that was set, not the one before")
        self.idle.run()
        self.assertEqual([name for name, _ in self.calls].count("open"), 1)
        self.assertEqual(self.others(), [])


if __name__ == "__main__":
    unittest.main()
