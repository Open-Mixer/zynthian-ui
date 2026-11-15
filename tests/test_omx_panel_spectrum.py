# -*- coding: utf-8 -*-
#
# The spectrum under a curve in the panel widget (zyngui/zynthian_widget_omx_panel.py; openmixer's spec 2026-11-15,
# zynthian RTA §6): while a panel whose display takes a spectrum is shown, omx-rta-read runs as its child with the taps
# the mode shows; hidden, rebuilt or destroyed, the child is ended and reaped. The reader is tests/stub_omx_rta_read.py
# (no JACK), the view a stand-in that takes a spectrum on the displays it is told, the graph a stand-in with one client,
# fx. The widget is imported under stand-ins for Tk, the GUI config and zynautoconnect, taken out again afterwards.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
STUB_READER = os.path.join(HERE, "stub_omx_rta_read.py")
for _name in ("pexpect", "pyliblo3", "zynconf", "zyncoder", "zyncoder.zyncore"):
    sys.modules.setdefault(_name, mock.MagicMock())
if "zyngine" not in sys.modules:  # the package without its __init__ (the engines and the hardware)
    _pkg = types.ModuleType("zyngine")
    _pkg.__path__ = [os.path.join(ROOT, "zyngine")]
    sys.modules["zyngine"] = _pkg
from test_omx_panel_view import FakeView, alive  # noqa: E402


def _graph(pattern, is_input=None):
    graph = [("fx:in_1", True), ("fx:out_1", False), ("fx:out_2", False)]
    return [types.SimpleNamespace(name=n, is_audio=True) for n, inp in graph
            if n.startswith(pattern.lstrip("^")) and (is_input is None or inp == is_input)]


def _import_widget():
    # the gestures, the position law and the touch layer are not the spectrum's: stand-ins, for the import only
    lent = ("zyngine.zynthian_panel_gestures", "zyngine.zynthian_position_law", "zyngine.zynthian_touch_layer")
    names = ("tkinter", "zynautoconnect", "zyngui", "zyngui.zynthian_gui_config", "zyngui.zynthian_widget_base",
             "zyngui.zynthian_widget_omx_panel") + lent
    saved = {n: sys.modules.get(n) for n in names}
    tk = types.ModuleType("tkinter")
    tk.Canvas, tk.FLAT = type("Canvas", (), {}), "flat"
    auto = types.ModuleType("zynautoconnect")
    auto.get_ports = _graph
    gui = types.ModuleType("zyngui")
    gui.__path__ = [os.path.join(ROOT, "zyngui")]
    base = types.ModuleType("zyngui.zynthian_widget_base")

    class zynthian_widget_base:  # what the widget uses of the base: shown, show, hide and destroy
        shown = False
        destroyed = False

        def show(self):
            self.shown = True

        def hide(self):
            self.shown = False

        def destroy(self):
            self.destroyed = True
    base.zynthian_widget_base = zynthian_widget_base
    sys.modules.update({"tkinter": tk, "zynautoconnect": auto, "zyngui": gui, "zyngui.zynthian_gui_config": mock.MagicMock(),
                        "zyngui.zynthian_widget_base": base})
    gui.zynthian_gui_config = sys.modules["zyngui.zynthian_gui_config"]
    pkg = sys.modules["zyngine"]
    lent_saved = {n: getattr(pkg, n.split(".")[1], None) for n in lent}
    for n in lent:
        sys.modules[n] = mock.MagicMock()
        setattr(pkg, n.split(".")[1], sys.modules[n])
    try:
        return importlib.import_module("zyngui.zynthian_widget_omx_panel")
    finally:
        for n, m in lent_saved.items():
            if m is None:
                delattr(pkg, n.split(".")[1])
            else:
                setattr(pkg, n.split(".")[1], m)
        for n, m in saved.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m


widget_mod = _import_widget()


class PanelSpectrum(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.chmod(STUB_READER, os.stat(STUB_READER).st_mode | stat.S_IXUSR)
        os.makedirs(os.path.join(self.tmp, "c", "3", "omx-dsp", "kernels"))
        with open(os.path.join(self.tmp, "c", "3", "omx-dsp", "kernels", "rta.json"), "w") as f:
            json.dump({"constants": {"RTA_LEVEL_DB_MIN": {"value": -72}, "RTA_LEVEL_DB_MAX": {"value": 0},
                                     "RTA_LEVEL_GRID_DB": {"value": 12}}}, f)
        self.pidfile, self.argvfile = os.path.join(self.tmp, "pid"), os.path.join(self.tmp, "argv")
        patch = mock.patch.dict(os.environ, {"ZYNTHIAN_OMX_RTA_READ": STUB_READER, "OMX_CONTRACT_PATH": os.path.join(self.tmp, "c"),
                                             "STUB_RTA_PIDFILE": self.pidfile, "STUB_RTA_ARGV": self.argvfile})
        patch.start()
        self.addCleanup(patch.stop)

    def widget(self, takes=(0,), sharing=(5,), instance=5):
        w = widget_mod.zynthian_widget_omx_panel.__new__(widget_mod.zynthian_widget_omx_panel)
        w.shown, w.width, w.height = True, 480, 300
        w.drawn, w.display_map, w.spectrum = FakeView(takes), {0: 0}, None
        w.rta_mode, w.rta_delta = "post", False
        engine = types.SimpleNamespace(name="Fx", instance=instance, rta_sharing=lambda p: list(sharing))
        w.processor = types.SimpleNamespace(engine=engine, get_jackname=lambda: "fx")
        self.addCleanup(w.stop_spectrum)
        return w

    def pid(self):
        deadline = time.monotonic() + 5
        while not (os.path.exists(self.pidfile) and open(self.pidfile).read()):
            self.assertLess(time.monotonic(), deadline, "the reader never started")
            time.sleep(0.01)
        return int(open(self.pidfile).read())

    def argv(self):
        deadline = time.monotonic() + 5
        while not (os.path.exists(self.argvfile) and open(self.argvfile).read()):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        return open(self.argvfile).read().split()

    def test_a_shown_curve_panel_shows_the_spectrum(self):
        w = self.widget()
        self.assertTrue(w.start_spectrum())
        deadline = time.monotonic() + 5
        while not w.spectrum.apply():
            self.assertLess(time.monotonic(), deadline, "no frame reached the view")
            time.sleep(0.01)
        display, frame, mode, delta, window = w.drawn.calls[-1]
        self.assertEqual((display, mode, delta, window), (0, "post", False, (-72.0, 0.0, 12.0)))
        self.assertEqual(self.argv(), ["--post", "fx:out_1", "--post", "fx:out_2", "--bands", "64"])

    def test_hidden_the_reader_is_gone(self):
        w = self.widget()
        w.start_spectrum()
        pid = self.pid()
        w.hide()
        self.assertFalse(alive(pid), "the reader outlived the hidden panel")
        self.assertIsNone(w.spectrum)

    def test_destroyed_the_reader_is_gone(self):
        w = self.widget()
        w.start_spectrum()
        pid = self.pid()
        w.destroy()
        self.assertFalse(alive(pid), "the reader outlived the destroyed panel")
        self.assertTrue(w.destroyed)

    def test_shown_again_the_reader_starts_again(self):
        w = self.widget()
        w.start_spectrum()
        first = self.pid()
        w.hide()
        os.unlink(self.pidfile)
        w.show()
        self.assertNotEqual(self.pid(), first)
        self.assertTrue(w.spectrum.running)

    def test_a_mode_change_reads_the_new_taps_and_ends_the_old_reader(self):
        w = self.widget()
        w.start_spectrum()
        first = self.pid()
        os.unlink(self.pidfile), os.unlink(self.argvfile)
        w.set_rta_mode("pre")
        self.assertFalse(alive(first), "the post reader was ended")
        self.assertEqual(self.argv(), ["--pre", "fx:in_1", "--bands", "64"])

    def test_a_panel_whose_displays_take_no_spectrum_starts_no_reader(self):
        w = self.widget(takes=())
        self.assertFalse(w.start_spectrum())
        time.sleep(0.2)
        self.assertFalse(os.path.exists(self.pidfile))

    def test_a_member_inside_a_grouped_chain_starts_no_reader_and_says_why(self):
        w = self.widget(sharing=(3, 5, 7), instance=5)
        with self.assertLogs(level="WARNING") as logs:
            self.assertFalse(w.start_spectrum())
        self.assertIn("no spectrum inside a grouped chain", logs.output[0])
        self.assertFalse(os.path.exists(self.pidfile))


if __name__ == "__main__":
    unittest.main()
