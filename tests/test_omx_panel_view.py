# -*- coding: utf-8 -*-
#
# The drawn view of a plugin-hostd panel (zyngine/zynthian_omx_panel_view.py): which part of the panel a screen shows,
# the curve_bind line plugin-hostd draws a display from, the replies it reads back, and, where omx-panel's renderer is
# installed ($ZYNTHIAN_OMX_PANEL_RENDER and $ZYNTHIAN_OMX_PANEL_TOOLS in CI, built from the omx-panel commit the
# workflow names), the renderer drawing the bars, a curve and a meter by value. The fixtures are `omx-panel describe
# --layout` and `omx-panel describe` of omx-plugins' omx-eq8, omx-geq and omx-comp descriptors.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "omx_panel")
_spec = importlib.util.spec_from_file_location("omx_panel_view", os.path.join(HERE, "..", "zyngine", "zynthian_omx_panel_view.py"))
view = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(view)


def fixture(name):
    with open(os.path.join(FIXTURES, f"{name}.json")) as f:
        return json.load(f)


def renderer():
    try:
        view.library()
        return True
    except view.RendererAbsent:
        return False


class ScreenPart(unittest.TestCase):

    def test_a_band_page_shows_its_section_and_the_curve_above_it(self):
        layout = fixture("omx-eq8")["layout"]
        part, displays = view.screen_part(layout, {"b2_freq", "b2_gain", "b2_q", "b2_on"})
        # omx-panel 0.17 lays the bands out as one matrix section, every band's controls in it
        self.assertEqual([s["key"] for s in part["sections"]], ["bands.band_1"])
        self.assertEqual([d["kind"] for d in part["displays"]], ["eq_response"])
        self.assertEqual(displays, {0: 0})
        # the controls keep their section, renumbered to the part's
        self.assertEqual({c["symbol"]: c["section"] for c in part["controls"] if c["symbol"].startswith("b2_")},
                         {"b2_type": 0, "b2_freq": 0, "b2_gain": 0, "b2_q": 0, "b2_on": 0})
        self.assertTrue(all(0 <= c["section"] < len(part["sections"]) for c in part["controls"]))

    def test_a_graphic_eq_page_shows_the_whole_row_of_bars(self):
        layout = fixture("omx-geq")["layout"]
        part, displays = view.screen_part(layout, {"band05", "band06", "band07", "band08"})
        self.assertEqual([s["key"] for s in part["sections"]], ["geq"])
        self.assertEqual(sum(len(b["controls"]) for b in part["sections"][0]["bars"]), 31)
        self.assertEqual(displays, {})

    def test_the_meters_stand_on_every_page(self):
        layout = fixture("omx-comp")["layout"]
        part, _ = view.screen_part(layout, {"duckOn"})
        self.assertEqual([m["symbol"] for m in part["meters"]], [m["symbol"] for m in layout["meters"]])
        self.assertIn("comp", [s["key"] for s in part["sections"]], "the transfer curve's section")

    def test_what_has_a_drawn_view(self):
        for name in ("omx-eq8", "omx-geq", "omx-comp"):
            self.assertTrue(view.drawn_parts(fixture(name)["layout"]), name)
        plain = dict(fixture("omx-geq")["layout"], sections=[{"key": "x", "label": "X"}], displays=[], meters=[])
        self.assertFalse(view.drawn_parts(plain))


class CurveBinding(unittest.TestCase):

    def test_a_dynamics_curve_is_bound_by_the_roles_omx_dsp_names_only(self):
        # CURVE_ROLES is one set for every family (0.32.4 added the drive's and the time family's, mix among them): a
        # term the family's curve does not read is no term of it, so the compressor's mix is bound and draws nothing
        line = view.curve_bind_line(7, 0, fixture("omx-comp")["description"])
        # the units are the standard ids the description serves (omx-panel 0.17): curve_bind takes :dB and refuses :db
        self.assertEqual(line, "curve_bind 7 0 transfer_curve dynamics threshold=thresholdDb:dB ratio=ratio:ratio "
                               "knee=kneeDb:dB makeup=makeupDb:dB mix=mixPct:percent")
        self.assertNotIn("attack", line)
        self.assertNotIn("release", line)

    def test_an_eq_curve_indexes_its_bands(self):
        line = view.curve_bind_line(3, 0, fixture("omx-eq8")["description"]).split()
        self.assertEqual(line[:5], ["curve_bind", "3", "0", "eq_response", "eq"])
        self.assertIn("hpf_freq=hpf_freq:Hz", line)
        self.assertIn("band_freq.0=b1_freq:Hz", line)
        self.assertIn("band_gain.7=b8_gain:dB", line)

    def test_shapes_follow_the_role(self):
        d = {"family": "eq", "displays": [{"kind": "eq_response"}],
             "roles": [{"role": "band_type", "index": 0, "symbol": "t", "unit": "none", "shapes": ["bell", "notch"]},
                       {"role": "band_freq", "index": 1, "symbol": "f", "unit": "hz", "shape": "lowshelf"}]}
        self.assertEqual(view.curve_bind_line(1, 0, d),
                         "curve_bind 1 0 eq_response eq band_type.0=t:none@bell|notch band_freq.1=f:hz@lowshelf")

    def test_a_display_that_is_no_curve_binds_nothing(self):
        d = {"family": "dynamics", "displays": [{"kind": "gain_reduction_bar"}], "roles": []}
        self.assertIsNone(view.curve_bind_line(1, 0, d))

    def declaration(self, displays, roles):
        """A contract directory holding only omx-dsp's curve.json with these ids; OMX_CONTRACT_PATH names it."""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        os.makedirs(os.path.join(root, "omx-dsp", "primitives"))
        with open(os.path.join(root, "omx-dsp", "primitives", "curve.json"), "w") as f:
            json.dump({"CURVE_DISPLAYS": {"ids": displays}, "CURVE_ROLES": {"ids": roles}}, f)
        patch = mock.patch.dict(os.environ, {"OMX_CONTRACT_PATH": root + ":/nowhere"})
        patch.start()
        self.addCleanup(patch.stop)
        return root

    def test_the_kinds_and_roles_are_the_owners_in_the_wires_spelling(self):
        kinds, roles = view.curve_words()   # the installed omx-dsp-contract
        self.assertIn("eq_response", kinds)
        self.assertIn("transfer_curve", kinds)
        self.assertIn("knee_start", roles)
        self.assertNotIn("kneeStart", roles)

    def test_a_role_the_owner_adds_is_bound_and_one_it_drops_is_not(self):
        self.declaration(["transferCurve", "phaseResponse"], ["threshold", "lookAhead"])
        d = {"family": "dynamics", "displays": [{"kind": "transfer_curve"}, {"kind": "phase_response"}, {"kind": "eq_response"}],
             "roles": [{"role": "threshold", "symbol": "t", "unit": "db"}, {"role": "look_ahead", "symbol": "l", "unit": "ms"},
                       {"role": "ratio", "symbol": "r", "unit": "ratio"}]}
        self.assertEqual(view.curve_bind_line(1, 0, d), "curve_bind 1 0 transfer_curve dynamics threshold=t:db look_ahead=l:ms")
        self.assertTrue(view.curve_bind_line(1, 1, d).startswith("curve_bind 1 1 phase_response "))
        self.assertIsNone(view.curve_bind_line(1, 2, d))

    def test_with_no_declaration_no_display_is_a_curve(self):
        root = self.declaration([], [])
        shutil.rmtree(os.path.join(root, "omx-dsp"))
        with self.assertLogs(level="WARNING") as logs:
            self.assertIsNone(view.curve_bind_line(7, 0, fixture("omx-comp")["description"]))
        self.assertIn("curve.json", logs.output[0])

    def test_the_module_keeps_no_copy_of_the_owners_words(self):
        with open(view.__file__) as f:
            source = f.read()
        for word in ("band_freq", "knee_start", "transfer_curve", "eq_response"):
            self.assertNotIn(f'"{word}"', source)

    def test_the_module_keeps_no_list_of_the_gesture_words(self):
        with open(view.__file__) as f:
            source = f.read()
        for word in ("drag", "second", "reset", "toggle", "paint"):
            self.assertNotIn(f'"{word}"', source)
        self.assertFalse(hasattr(view, "WORDS"))

    def test_a_library_that_is_not_the_renderer_is_refused_as_not_installed(self):
        # any library that lacks the renderer's functions is no renderer here
        with mock.patch.dict(os.environ, {"ZYNTHIAN_OMX_PANEL_RENDER": "libm.so.6"}), \
                mock.patch.object(view, "_lib", None), mock.patch.object(view, "_lib_error", None):
            with self.assertRaises(view.RendererAbsent) as refused:
                view.library()
            self.assertIn("is not installed", str(refused.exception))
            self.assertNotIn("older", str(refused.exception))

    def test_the_points_of_a_reply(self):
        """curve_points' reply is '<count> <marks> <x>,<y> ...' (plugin-hostd-protocol's curve-points-reply): the marks
        one word after the count, '-' when none, and a delay's taps after the points ('stems ...'). These are the
        replies the protocol's grammar test holds, and omx-comp's as plugin-hostd 0.22.4 answered it."""
        self.assertEqual(view.curve_points("8 - -80.00,-80.00 -68.57,-68.57 -57.14,-57.14 -45.71,-45.71 -34.29,-34.29 "
                                           "-22.86,-22.86 -11.43,-16.36 0,-13.50"),
                         [(-80.0, -80.0), (-68.57, -68.57), (-57.14, -57.14), (-45.71, -45.71), (-34.29, -34.29),
                          (-22.86, -22.86), (-11.43, -16.36), (0.0, -13.5)])
        self.assertEqual(view.curve_points("3 1000,-6.00,2.00,fbs-fixed 20.00,1.00 40.0,2.00 80.0,0.00"),
                         [(20.0, 1.0), (40.0, 2.0), (80.0, 0.0)], "a mark is no point")
        self.assertEqual(view.curve_points("2 - 0,-80.00 500.0,-80.00 stems 1 0,0.00,1.000,right"),
                         [(0.0, -80.0), (500.0, -80.0)], "the taps after the points are no point")
        self.assertEqual(view.curve_points("0 -"), [])
        for bad in ("", "3 - 1,2 3,4", "2 - 1,2 nan,4", "x - 1,2", "2 1,2 3,4", "1 -"):
            self.assertEqual(view.curve_points(bad), [], bad)

    def test_a_feedback_line(self):
        self.assertEqual(view.output_set("output_set 2 compGr -3.5"), (2, "compGr", -3.5))
        self.assertIsNone(view.output_set("xruns 2"))
        self.assertIsNone(view.output_set("output_set 2 compGr x"))


@unittest.skipUnless(renderer(), "omx-panel's renderer is not installed")
class Drawn(unittest.TestCase):
    """The renderer itself, through this module: what a value, a curve and a meter change in the pixels."""

    W, H = 480, 300

    def draw(self, v):
        return v.draw(self.W, self.H)[0]

    def differs(self, a, b):
        """The rows where two drawings differ."""
        rows = set()
        for y in range(self.H):
            if a[y * self.W * 4:(y + 1) * self.W * 4] != b[y * self.W * 4:(y + 1) * self.W * 4]:
                rows.add(y)
        return rows

    def test_a_bar_moves_with_its_value_and_nothing_else_does(self):
        part, _ = view.screen_part(fixture("omx-geq")["layout"], {"band01"})
        v = view.View(part)
        i = v.symbols.index("band01")
        for k in range(len(v.symbols)):
            v.set_value(k, 0.5, "0 dB")
        before = self.draw(v)
        v.set_value(i, 1.0, "+12 dB")
        after = self.draw(v)
        self.assertTrue(self.differs(before, after), "the bar moved")
        v.set_value(i, 0.5, "0 dB")
        self.assertEqual(self.draw(v), before, "and came back")

    def test_a_curve_is_drawn_from_the_points_given(self):
        part, displays = view.screen_part(fixture("omx-comp")["layout"], {"thresholdDb"})
        v = view.View(part)
        empty = self.draw(v)
        self.assertTrue(v.set_curve(0, [(-80.0, -80.0), (-18.0, -18.0), (0.0, -13.5)]))
        drawn = self.draw(v)
        self.assertTrue(self.differs(empty, drawn))
        self.assertFalse(v.set_curve(0, [(0.0, 1.0)]), "one point is refused")
        self.assertEqual(self.draw(v), drawn, "and changes nothing")

    def test_a_meter_fills_to_its_reading(self):
        part, _ = view.screen_part(fixture("omx-comp")["layout"], {"thresholdDb"})
        v = view.View(part)
        frame = self.draw(v)
        self.assertTrue(v.set_meter(0, -12.0, 0.0))
        self.assertTrue(self.differs(frame, self.draw(v)))

    def test_the_word_names_are_the_librarys_in_the_declared_order(self):
        # omx-panel's schema/gestures.json, the file the gesture tests read too
        with open(os.environ["ZYNTHIAN_OMX_GESTURES"]) as f:
            words = list(json.load(f)["words"])
        # OMX_PANEL_WORD_NONE is 0, the declared words follow it in gestures.json's order
        self.assertEqual([view.word_name(k + 1) for k in range(len(words))], words)
        self.assertEqual(view.word_name(0), "")
        self.assertIsNone(view.word_name(len(words) + 1))

    def test_a_drag_moves_a_bar_through_the_gestures(self):
        part, _ = view.screen_part(fixture("omx-geq")["layout"], {"band01"})
        v = view.View(part)
        v.set_surface(self.W, self.H)
        i = v.symbols.index("band01")
        v.set_travel(i, -12.0, 12.0, 0.0)
        v.set_value(i, 0.5, "0 dB")
        (x, y, w, h), travel = v.target_rect(i)
        # a press on the bar's track and a drag up, past the drag's threshold, by half its travel
        cx, cy = x + w / 2, y + h / 2
        v.input(view.EVENT_DOWN, 0.0, cx, cy)
        for k in range(1, 11):
            changes, word, _ = v.input(view.EVENT_MOVE, 10.0 * k, cx, cy - k * travel / 20)
        v.input(view.EVENT_UP, 120.0, cx, cy - travel / 2)
        self.assertEqual(word, "drag")
        self.assertTrue(changes, "a press and a drag on a bar moved it")
        self.assertEqual([c[0] for c in changes], [i])
        _, fraction, value = changes[0]
        self.assertGreater(fraction, 0.5)
        self.assertAlmostEqual(value, -12.0 + 24.0 * fraction, places=6)  # the value is the travel's, -12..12


STUB_READER = os.path.join(HERE, "stub_omx_rta_read.py")


def alive(pid):
    """Whether a process `pid` exists and is not a zombie waiting for its parent."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(") ")[-1][:1] != "Z"
    except OSError:
        return False


class SpectrumCall(unittest.TestCase):
    """_LibraryView.set_spectrum (what View.set_spectrum forwards to) against omx-panel 0.14.0's entry: omx_panel_view_set_spectrum(view, display, hz, pre_db, post_db,
    peak_db, n, mode, delta, db_min, db_max, grid_db), mode omx_panel_tap_mode_t (PRE 0, POST 1, BOTH 2), the delta only
    with both; the library is libomx-panel-render.so.1, the soname that signature moved to."""

    WINDOW = (-72.0, 0.0, 12.0)
    FRAME = {"hz": [100.0, 1000.0, 10000.0], "pre": ([-30.0, -24.0, float("-inf")], [-27.0, -21.0, float("-inf")]),
             "post": ([-30.0, -12.0, float("-inf")], [-27.0, 0.0, float("-inf")]), "diff": [0.0, 12.0, None]}

    class Lib:
        def __init__(self):
            self.calls = []

        def omx_panel_view_set_spectrum(self, *args):
            # what ctypes would pass: arrays read back as lists, NULL as None
            self.calls.append(tuple(list(a) if hasattr(a, "_length_") else a for a in args))
            return True

        def omx_panel_view_destroy(self, v):
            pass

    def view(self):
        # the renderer process's side of View.set_spectrum (View forwards the call to it): the ctypes call itself
        v = view._LibraryView.__new__(view._LibraryView)
        v.lib, v.view = self.Lib(), "the view"
        return v

    def test_the_library_is_the_soname_the_new_entry_has(self):
        self.assertEqual(view.LIBRARY, "libomx-panel-render.so.1")

    def test_the_entry_is_declared_with_both_taps_the_mode_and_the_delta(self):
        lib = types.SimpleNamespace(omx_panel_view_set_spectrum=types.SimpleNamespace())
        view._declare_spectrum(lib)
        f = lib.omx_panel_view_set_spectrum
        self.assertEqual(f.restype, view.ctypes.c_bool)
        DP = view.ctypes.POINTER(view.ctypes.c_double)
        self.assertEqual(f.argtypes, [view.ctypes.c_void_p, view.ctypes.c_uint32, DP, DP, DP, DP, view.ctypes.c_uint32,
                                      view.ctypes.c_int, view.ctypes.c_bool, view.ctypes.c_double, view.ctypes.c_double,
                                      view.ctypes.c_double])

    def test_each_mode_hands_the_renderer_the_taps_it_shows(self):
        hz, pre, post = self.FRAME["hz"], self.FRAME["pre"], self.FRAME["post"]
        for mode, delta, want in (
                ("pre", False, (pre[0], None, pre[1], 0, False)),
                ("post", False, (None, post[0], post[1], 1, False)),
                ("both", False, (pre[0], post[0], post[1], 2, False)),
                ("both", True, (pre[0], post[0], post[1], 2, True)),
                ("post", True, (None, post[0], post[1], 1, False))):
            v = self.view()
            self.assertTrue(v.set_spectrum(3, self.FRAME, mode, delta, self.WINDOW))
            self.assertEqual(v.lib.calls, [("the view", 3, hz, *want[:3], 3, *want[3:], *self.WINDOW)], (mode, delta))

    def test_both_with_one_tap_answered_draws_that_tap_alone(self):
        v = self.view()
        v.set_spectrum(0, dict(self.FRAME, pre=None), "both", True, self.WINDOW)
        self.assertEqual(v.lib.calls[-1][3:9], (None, self.FRAME["post"][0], self.FRAME["post"][1], 3, 1, False))

    def test_no_frame_clears_it(self):
        v = self.view()
        self.assertTrue(v.set_spectrum(0, None, "both", True, self.WINDOW))
        self.assertEqual(v.lib.calls, [("the view", 0, None, None, None, None, 0, 1, False, *self.WINDOW)])

    def test_a_mode_that_is_none_of_the_three_is_refused_without_a_call(self):
        v = self.view()
        self.assertFalse(v.set_spectrum(0, self.FRAME, "sideways", False, self.WINDOW))
        self.assertEqual(v.lib.calls, [])


@unittest.skipUnless(renderer(), "omx-panel's renderer is not installed")
class SpectrumDrawn(unittest.TestCase):
    """The renderer itself: the modes and the delta change the pixels, and the delta is refused without both."""

    W, H = 480, 300
    WINDOW = (-72.0, 0.0, 12.0)

    def frame(self):
        hz = [20.0 * 1000.0 ** (k / 15) for k in range(16)]
        post = [-30.0 - (6.0 if 6 <= k <= 9 else 0.0) for k in range(16)]
        pre = [-30.0] * 16
        return {"hz": hz, "pre": (pre, [p + 3 for p in pre]), "post": (post, [p + 3 for p in post]), "diff": None}

    def view(self):
        layout = fixture("omx-eq8")["layout"]
        part, displays = view.screen_part(layout, {layout["controls"][0]["symbol"]})
        return view.View(part), displays

    def test_both_and_the_delta_each_draw_something_else(self):
        v, displays = self.view()
        d = next(iter(displays))
        f = self.frame()
        pics = {}
        for mode, delta in (("post", False), ("both", False), ("both", True)):
            self.assertTrue(v.set_spectrum(d, f, mode, delta, self.WINDOW), (mode, delta))
            pics[(mode, delta)] = v.draw(self.W, self.H)[0]  # the pixels; the second item is the rectangles it repainted
        self.assertNotEqual(pics[("post", False)], pics[("both", False)], "PRE's dim line is drawn in both")
        self.assertNotEqual(pics[("both", False)], pics[("both", True)], "the delta's wedges are drawn")
        self.assertTrue(v.set_spectrum(d, f, "post", False, self.WINDOW))
        self.assertEqual(v.draw(self.W, self.H)[0], pics[("post", False)], "and post alone comes back")


class FakeView:
    """What SpectrumFeed hands frames to: each set_spectrum call, recorded, accepted for the displays it has."""

    def __init__(self, displays=(0,)):
        self.displays, self.calls = set(displays), []

    def set_spectrum(self, display, frame, mode, delta, window):
        self.calls.append((display, frame, mode, delta, window))
        return display in self.displays


class SpectrumLines(unittest.TestCase):
    """The reader's JSON lines (spec §3: {"at", "rate", "hz", "post": {"db", "peak"}, "pre": {...}, "diff"})."""

    def test_a_frame_is_read_with_silence_as_minus_infinity(self):
        f = view.rta_frame('{"at":4,"rate":48000,"hz":[20,200,2000],"post":{"db":[-30,null,-12],"peak":[-27,null,0]}}')
        self.assertEqual(f["hz"], [20.0, 200.0, 2000.0])
        self.assertEqual(f["post"], ([-30.0, float("-inf"), -12.0], [-27.0, float("-inf"), 0.0]))
        self.assertIsNone(f["pre"])
        self.assertIsNone(f["diff"])

    def test_a_line_that_is_no_frame_is_none(self):
        for bad in ("", "not a frame", "{}", '{"hz":[20,10],"post":{"db":[1,2],"peak":[1,2]}}',
                    '{"hz":[20,200],"post":{"db":[1],"peak":[1,2]}}', '{"hz":[20,200]}',
                    '{"hz":[0,200],"post":{"db":[1,2],"peak":[1,2]}}', '{"hz":[20,200],"post":{"db":["x",2],"peak":[1,2]}}'):
            self.assertIsNone(view.rta_frame(bad), bad)

    def test_the_taps_follow_the_mode(self):
        self.assertEqual(view.rta_argv("post", ["fx:out_1"], ["fx:in_1"], 64, exe="r"), ["r", "--post", "fx:out_1", "--bands", "64"])
        self.assertEqual(view.rta_argv("pre", ["fx:out_1"], ["fx:in_1", "fx:in_2"], 32, exe="r"),
                         ["r", "--pre", "fx:in_1", "--pre", "fx:in_2", "--bands", "32"])
        self.assertEqual(view.rta_argv("both", ["fx:out_1"], ["fx:in_1"], 64, exe="r"),
                         ["r", "--post", "fx:out_1", "--pre", "fx:in_1", "--bands", "64"])

    def ports(self, pattern, is_input=None):
        """A graph of two clients, fx (two audio ins, two audio outs and a MIDI in) and other; the pattern as jack's."""
        graph = [("fx:in_1", True, True), ("fx:in_2", True, True), ("fx:out_1", False, True), ("fx:out_2", False, True),
                 ("fx:midi_in", True, False), ("other:out_1", False, True)]
        return [types.SimpleNamespace(name=n, is_audio=audio, is_input=inp) for n, inp, audio in graph
                if n.startswith(pattern.lstrip("^").replace("\\", "")) and (is_input is None or inp == is_input)]

    def test_a_client_of_its_own_answers_both_taps(self):
        self.assertEqual(view.rta_taps("fx", [5], 5, self.ports), (["fx:out_1", "fx:out_2"], ["fx:in_1", "fx:in_2"], None))

    def test_inside_a_grouped_chain_only_the_ends_answer(self):
        self.assertEqual(view.rta_taps("fx", [3, 4, 5], 3, self.ports), ([], ["fx:in_1", "fx:in_2"], None), "the first: pre only")
        self.assertEqual(view.rta_taps("fx", [3, 4, 5], 5, self.ports), (["fx:out_1", "fx:out_2"], [], None), "the last: post only")
        post, pre, refusal = view.rta_taps("fx", [3, 4, 5], 4, self.ports)
        self.assertEqual((post, pre), ([], []), "a middle member is never given another signal's spectrum")
        self.assertEqual(refusal, "no spectrum inside a grouped chain")

    def test_no_client_answers_nothing(self):
        self.assertEqual(view.rta_taps(None, [5], 5, self.ports)[:2], ([], []))

    def test_the_level_window_is_omx_dsps_declaration(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        # the shape omx-dsp installs: its kernel declarations' rta.json, the constants under "constants", in its owner's
        # directory of the contract directory (no schema-major level)
        os.makedirs(os.path.join(root, "omx-dsp", "kernels"))
        with open(os.path.join(root, "omx-dsp", "kernels", "rta.json"), "w") as f:
            json.dump({"constants": {"RTA_LEVEL_DB_MIN": {"kind": "scalar", "unit": "dB", "value": -90},
                                     "RTA_LEVEL_DB_MAX": {"kind": "scalar", "unit": "dB", "value": 6},
                                     "RTA_LEVEL_GRID_DB": {"kind": "scalar", "unit": "dB", "value": 6}}}, f)
        self.assertEqual(view.rta_window(root), (-90.0, 6.0, 6.0))
        with self.assertLogs(level="WARNING"):
            self.assertIsNone(view.rta_window(os.path.join(root, "nowhere")))

    def test_a_mode_whose_taps_are_not_answered_reads_nothing(self):
        self.assertIsNone(view.rta_argv("post", [], ["fx:in_1"], 64, exe="r"))
        self.assertIsNone(view.rta_argv("both", ["fx:out_1"], [], 64, exe="r"))
        self.assertIsNone(view.rta_argv("sideways", ["fx:out_1"], ["fx:in_1"], 64, exe="r"))


class SpectrumReader(unittest.TestCase):
    """The reader as the panel's child (spec §6): started while a curve panel is shown, its frames handed to the view,
    ended and reaped on close, whatever it does."""

    WINDOW = (-72.0, 0.0, 12.0)

    def feed(self, env=None, mode="post", fake=None, argv=None):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        pidfile = os.path.join(tmp, "pid")
        patch = mock.patch.dict(os.environ, dict(env or {}, STUB_RTA_PIDFILE=pidfile))
        patch.start()
        self.addCleanup(patch.stop)
        argv = argv or [sys.executable, STUB_READER] + view.rta_argv(mode, ["fx:out_1"], ["fx:in_1"], 16, exe="omx-rta-read")[1:]
        fake = fake or FakeView()
        f = view.SpectrumFeed(fake, [0], argv, mode, False, self.WINDOW)
        self.addCleanup(f.stop)
        return f, fake, pidfile

    def pid(self, pidfile):
        deadline = time.monotonic() + 5
        while not os.path.exists(pidfile) or not open(pidfile).read():
            self.assertLess(time.monotonic(), deadline, "the reader never started")
            time.sleep(0.01)
        return int(open(pidfile).read())

    def first(self, f):
        deadline = time.monotonic() + 5
        while not f.apply():
            self.assertLess(time.monotonic(), deadline, "no frame reached the view")
            time.sleep(0.01)

    def test_a_curve_panel_shows_the_readers_spectrum(self):
        f, fake, _ = self.feed()
        self.assertTrue(f.start())
        self.first(f)
        display, frame, mode, delta, window = fake.calls[-1]
        self.assertEqual((display, mode, delta, window), (0, "post", False, self.WINDOW))
        self.assertEqual(len(frame["hz"]), 16)
        self.assertEqual(frame["post"][0][:2], [-30.0, -31.0])
        self.assertFalse(f.apply(), "no new frame, nothing handed again")

    def test_until_the_first_line_nothing_is_handed(self):
        f, fake, _ = self.feed()
        self.assertFalse(f.apply())
        self.assertEqual(fake.calls, [])

    def test_the_reader_is_gone_after_close(self):
        f, _, pidfile = self.feed()
        f.start()
        self.first(f)
        pid = self.pid(pidfile)
        self.assertTrue(alive(pid))
        f.stop()
        self.assertFalse(alive(pid), "the reader outlived the panel")
        self.assertFalse(f.running)
        f.stop()  # twice is nothing

    def test_a_reader_that_ignores_sigterm_is_still_gone_after_close(self):
        f, _, pidfile = self.feed(env={"STUB_RTA_IGNORE_TERM": "1"})
        f.start()
        self.first(f)
        pid = self.pid(pidfile)
        self.addCleanup(lambda: alive(pid) and os.kill(pid, signal.SIGKILL))  # a failed stop leaves no stray
        # bounded: a stop that only asks would wait on the reader for ever; this test fails instead of hanging
        stopping = threading.Thread(target=f.stop, kwargs={"grace": 0.3}, daemon=True)
        stopping.start()
        stopping.join(5)
        self.assertFalse(stopping.is_alive(), "stop() still waits on a reader deaf to SIGTERM after 5 s")
        self.assertFalse(alive(pid), "a reader deaf to SIGTERM outlived the panel")

    def test_the_reader_runs_in_its_own_process_group(self):
        f, _, pidfile = self.feed()
        f.start()
        pid = self.pid(pidfile)
        self.assertEqual(os.getpgid(pid), pid)
        self.assertNotEqual(os.getpgid(pid), os.getpgid(0))

    def test_a_reader_that_ends_by_itself_leaves_no_spectrum_and_is_said_once(self):
        f, fake, pidfile = self.feed(env={"STUB_RTA_EXIT_AFTER": "2"})
        with self.assertLogs(level="WARNING") as logs:
            f.start()
            deadline = time.monotonic() + 5
            while f.running:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            f.apply()
        self.assertEqual(len([m for m in logs.output if "omx-rta-read" in m]), 1, logs.output)
        self.assertIn("status 3", logs.output[0])
        self.assertFalse(alive(self.pid(pidfile)), "reaped")
        self.assertEqual(fake.calls[-1][1], None, "the spectrum is cleared once the reader is gone")

    def test_a_line_that_is_no_frame_is_skipped(self):
        f, fake, _ = self.feed(env={"STUB_RTA_BAD_FIRST": "1"})
        f.start()
        self.first(f)
        self.assertTrue(all(c[1] is None or len(c[1]["hz"]) == 16 for c in fake.calls))

    def test_a_missing_reader_is_named_and_nothing_runs(self):
        f, fake, _ = self.feed(argv=["/nowhere/omx-rta-read", "--post", "fx:out_1", "--bands", "16"])
        with self.assertLogs(level="WARNING") as logs:
            self.assertFalse(f.start())
        self.assertIn("omx-rta-read", logs.output[0])
        self.assertFalse(f.running)
        self.assertEqual(fake.calls, [])

    def test_both_hands_pre_post_and_the_mode(self):
        f, fake, _ = self.feed(mode="both")
        f.start()
        self.first(f)
        _, frame, mode, _, _ = fake.calls[-1]
        self.assertEqual(mode, "both")
        self.assertEqual(frame["pre"][0][0], float("-inf"))
        self.assertEqual(len(frame["diff"]), 16)

    def test_a_display_the_view_refuses_is_said_once_and_not_fed_again(self):
        f, fake, _ = self.feed(fake=FakeView(displays=()))
        with self.assertLogs(level="WARNING") as logs:
            f.start()
            deadline = time.monotonic() + 5
            while len(fake.calls) < 1:
                f.apply()
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            time.sleep(0.1)
            f.apply()
        self.assertEqual(len(fake.calls), 1, "a refused display is not fed every frame")
        self.assertEqual(len([m for m in logs.output if "spectrum" in m]), 1, logs.output)


class Feedback(unittest.TestCase):
    """The engine's feedback reader on a socket: the meters' last values by (instance, symbol)."""

    def test_the_last_value_of_each_output(self):
        import sys
        sys.path.insert(0, HERE)
        from test_engine_plugin_hostd import ph  # noqa: E402 (the engine module under the tests' stand-ins)
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        fb = ph.plugin_hostd_feedback(server.getsockname()[1])
        fb.connect()
        conn, _ = server.accept()
        conn.sendall(b"output_set 4 compGr -1.5\0xruns 1\0output_set 4 compGr -6.25\0output_set 5 lvl 0.5\0")
        deadline = time.monotonic() + 2
        while len(fb.values) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(fb.values, {(4, "compGr"): -6.25, (5, "lvl"): 0.5})
        self.assertEqual(fb.generation, 1)
        fb.close()
        conn.close()
        server.close()

    def test_no_feedback_port_is_said_and_nothing_else(self):
        import sys
        sys.path.insert(0, HERE)
        from test_engine_plugin_hostd import ph  # noqa: E402
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        fb = ph.plugin_hostd_feedback(port)
        fb.connect()
        self.assertIsNone(fb.sock)
        self.assertEqual(fb.values, {})


if __name__ == "__main__":
    unittest.main()
