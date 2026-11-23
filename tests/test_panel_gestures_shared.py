# -*- coding: utf-8 -*-
#
# The Python gesture engine against the SAME cases as omx-panel's reference (tools/gestures.mjs), and the position law it
# moves a control by against omx-contract's scale vectors. omx-panel's test/fixtures/gestures/scripts.json is the one set
# of scripted gestures its JavaScript reference (test/gestures.test.mjs) and its C reference (renderer/test/gesture-c.test.mjs)
# both run; this file runs every script of it that has a surface here (fader, bar group, and the handle's one-axis
# inputs) into zyngine.zynthian_panel_gestures and holds the engine to what omx-panel says: the word, the value within
# one declared step (a reset and a tap exact), what was selected, the count of gestures, nothing refused. The scripts are
# read from the omx-panel the table is read from (ZYNTHIAN_OMX_GESTURES, else the installed one) and never copied. The
# scripts that have no surface in this engine are named in NO_SURFACE with why, each held to still have none, and the
# number of scripts run is held, so a count that quietly fell would be red.
#
# omx-contract's data/scale-vectors.json (ZYNTHIAN_OMX_SCALE_VECTORS, else /usr/share/omx-contract/scale-vectors.json) is
# the golden table of the lin/log (and stepped, map) law: pg.Travel, the route the engine reaches the law by, must give
# each row's position and value within one ulp. Without the files the tests FAIL by name; there is no copy of either here.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_engine_plugin_hostd import ROOT  # noqa: F401,E402  (sets up the stand-ins the engine package imports)
from zyngine import zynthian_panel_gestures as pg  # noqa: E402

VECTORS_ENV = "ZYNTHIAN_OMX_SCALE_VECTORS"
VECTORS_INSTALLED = "/usr/share/omx-contract/scale-vectors.json"


def omx_panel(*path):
    """A file of the omx-panel tree whose schema/gestures.json is read."""
    try:
        return os.path.join(os.path.dirname(os.path.dirname(pg.table_path())), *path)
    except pg.GestureTableAbsent as e:
        raise AssertionError(f"omx-panel is absent ({e}): install it or set {pg.ENV_TABLE}")


def read(path, what):
    try:
        with open(path) as f:
            return json.load(f)
    except OSError as e:
        raise AssertionError(f"{what} is absent ({e}): this test keeps no copy of it")


def scripts():
    return read(omx_panel("test", "fixtures", "gestures", "scripts.json"), "omx-panel's gesture scripts")["scripts"]


class Member:
    """One control's declared travel and its value (the control the script moves)."""

    def __init__(self, travel, start=None):
        self.travel = {k: travel[k] for k in ("scale", "min", "max", "step") if k in travel}
        self.default = travel.get("default")
        self.value = start if start is not None else (self.default if self.default is not None else travel["min"])

    def set(self, v):
        self.value = v


def declared(descriptor):
    """symbol -> its declared travel, from the descriptor a script names (omx-panel's own)."""
    d = read(omx_panel(descriptor), f"the descriptor {descriptor}")
    return {c["symbol"]: c["travel"] for c in d["controls"] if "travel" in c and "symbol" in c}


def member(travel, **extra):
    """A script's own member (a bar of the 8-band group names its travel inline as min, max, def, scale)."""
    return Member({"scale": travel.get("scale", "linear"), "min": travel["min"], "max": travel["max"],
                   **({"default": travel["def"]} if "def" in travel else {})}, extra.get("start"))


class Run:
    """A script built into this engine's control, driven, and read back."""

    def __init__(self, s):
        self.s = s
        c = s["control"]
        self.words = []
        self.members = {}
        w = c["widget"]
        if w == "fader":
            m = Member(declared(s["descriptor"])[c["member"]], c["start"].get("value"))
            self.members = {"value": m}
            t = c["target"]
            self.engine = pg.Gestures("fader", pg.Travel(m.travel, m.default), lambda: m.value, m.set,
                                      (t["x"], t["y"], t["w"], t["h"]), travel_px=c["travelPx"], on_word=self.words.append)
        elif w == "bar":
            self.engine, self.members = self.bars(c, s.get("descriptor"))
        elif w == "handle":
            tr = declared(s["descriptor"])
            mem = {k: Member(tr[sym], c["start"].get(k)) for k, sym in c["members"].items()}
            self.members = mem
            g, q = mem["gain"], mem["q"]
            t = c["target"]
            self.engine = pg.Gestures("handle", pg.Travel(g.travel, g.default), lambda: g.value, g.set,
                                      (t["x"], t["y"], t["w"], t["h"]), orientation="horizontal", on_word=self.words.append,
                                      second=(pg.Travel(q.travel, q.default), lambda: q.value, q.set))
        else:
            raise AssertionError(f"no surface for a {w}")

    def bars(self, c, descriptor):
        if "members" in c:
            ms = {b["symbol"]: member(b, start=c.get("start", {}).get(b["symbol"])) for b in c["members"]}
            tg = {b["symbol"]: (b["target"]["x"], b["target"]["y"], b["target"]["w"], b["target"]["h"]) for b in c["members"]}
            order = [b["symbol"] for b in c["members"]]
        else:
            tr = declared(descriptor)
            g = c["geometry"]
            ms = {sym: Member(tr[sym], c["start"].get(sym)) for sym in c["symbols"]}
            tg = {sym: (i * g["pitch"], 0, g["w"], g["h"]) for i, sym in enumerate(c["symbols"])}
            order = c["symbols"]
        self.start = {k: m.value for k, m in ms.items()}
        self.order = order
        bars = [(pg.Travel(ms[k].travel, ms[k].default), (lambda k=k: ms[k].value), ms[k].set, tg[k]) for k in order]
        return pg.BarGroup(bars, on_word=lambda word, column=None: self.words.append((word, column))), ms

    def drive(self):
        e0 = self.engine
        for e in self.s["script"]:
            t, k = e["t"], e["type"]
            if k == "down":
                e0.press(e["x"], e["y"], t, e["id"], e["ptype"])
            elif k == "move":
                e0.motion(e["x"], e["y"], t, e["id"], fine=e.get("fine", False))
            elif k == "up":
                e0.release(e["x"], e["y"], t, e["id"])
            elif k == "wheel":
                e0.step(e["n"], t, coarse=e.get("coarse", False), source="wheel")
            elif k == "key":
                e0.key(e["key"], t, shift=e.get("shift", False))
            elif k == "detent":
                e0.step(e["n"], t, source="encoder3" if e.get("encoder") == 3 else "detent")
            else:
                raise AssertionError(f"no input {k}")
        return self

    @property
    def log(self):
        return self.engine.log

    @property
    def refused(self):
        return sum((b.refused for b in self.engine.bars), []) if isinstance(self.engine, pg.BarGroup) else self.engine.refused


# scripts omx-panel's references run that this engine has no surface for: Zynthian has no plot-position node (the omx-eq
# handle is dragged on a frequency-by-gain plot, here a handle is one row's one-value control), and no undo list. Each is
# held to still be a script of the file, so an entry cannot outlive the script it names.
NO_SURFACE = {
    "omx-eq band: drag the node": "a drag moves frequency and gain over the plot; a handle row here moves one value",
    "omx-eq band: fine drag is 0.3 of the drag": "the same plot drag, at the fine ratio",
    "omx-eq band: reset is the gain only, frequency and Q keep": "its double tap lands on the plot node and is preceded by the plot drag",
}


# scripts this engine answers DIFFERENTLY from omx-panel's reference (found by this test, not yet brought in line): the
# declaration's paint is touch required, mouse optional (schema/gestures.json), and the reference's mouse paints only where a
# surface asks for it (paintWithMouse); BarGroup paints on any pointer type.
DIVERGES = {
    "8-band graphic EQ: a mouse sweep drags the pressed bar and paints nothing":
        "BarGroup ignores the pointer type: a mouse sweep across columns paints, where the reference drags the pressed bar only",
}


def tolerance(travel, scale_fraction):
    """One declared step on the 0..1 travel, as omx-panel's test reads it: a stepped one's, a linear one's declared step,
    else the declaration's stepFraction."""
    if travel.get("scale") == "stepped":
        return 1.0 / (round((travel["max"] - travel["min"]) / travel["step"]))
    if travel.get("step") and travel.get("scale", "linear") == "linear":
        return travel["step"] / (travel["max"] - travel["min"])
    return scale_fraction


class SharedScripts(unittest.TestCase):
    def test_the_scripts_this_engine_runs_are_a_real_share_of_the_file(self):
        every = scripts()
        run = [s for s in every if s["name"] not in NO_SURFACE and s["name"] not in DIVERGES]
        self.assertGreaterEqual(len(every), 20)
        self.assertGreaterEqual(len(run), 16)
        self.assertEqual({s["control"]["widget"] for s in run}, {"fader", "bar", "handle"})
        for name in NO_SURFACE:
            self.assertIn(name, [s["name"] for s in every], f"{name} is no longer a script of omx-panel's file")

    def check(self, s):
        """Drive one script into the engine and hold it to omx-panel's expectation; AssertionError where it differs."""
        fraction = pg.load_table()["thresholds"]["stepFraction"]
        r = Run(s).drive()
        want = s["expect"]
        self.assertEqual(r.refused, [], "nothing refused")
        for key, w in (want["value"] if isinstance(want["value"], dict) else {"value": want["value"]}).items():
            m = r.members[key]
            if want["tolerance"] == "exact":
                self.assertEqual(m.value, w, f"{key} exact")
            else:
                t = pg.Travel(m.travel, m.default)
                self.assertLessEqual(abs(t.position(m.value) - t.position(w)), tolerance(m.travel, fraction) + 1e-9,
                                     f"{key}: {m.value} is within one declared step of {w}")
        if "changed" in want:
            moved = [k for k in r.order if r.members[k].value != r.start[k]]
            self.assertEqual(moved, want["changed"], "the bars that moved")
        self.assertEqual(r.log[-1]["word"], want["word"])
        if isinstance(r.engine, pg.BarGroup):
            if "gestures" in want:
                self.assertEqual(len(r.log), want["gestures"])
            if "selected" in want:
                self.assertIn(("select", r.order.index(want["selected"])), r.words)
        elif "selected" in want:
            self.assertIn("select", r.words)

    def test_every_script_lands_where_omx_panel_says(self):
        for s in scripts():
            if s["name"] in NO_SURFACE or s["name"] in DIVERGES:
                continue
            with self.subTest(s["name"]):
                self.check(s)

    def test_a_known_divergence_still_diverges(self):
        """Each entry of DIVERGES is a script this engine answers differently from omx-panel's reference today; it is held
        to still differ, so the day the engine is brought in line this goes red and the entry is deleted."""
        every = {s["name"]: s for s in scripts()}
        for name, why in DIVERGES.items():
            with self.subTest(name):
                self.assertIn(name, every, "no longer a script of omx-panel's file")
                with self.assertRaises(AssertionError, msg=f"{name} now matches the reference: delete its entry ({why})"):
                    self.check(every[name])


class ScaleVectors(unittest.TestCase):
    """pg.Travel (position() and value(): the route the engine moves a control by) on omx-contract's golden law rows."""

    @classmethod
    def setUpClass(cls):
        cls.doc = read(os.environ.get(VECTORS_ENV) or VECTORS_INSTALLED, "omx-contract's scale vectors")

    def near(self, got, want):
        return got == want or abs(got - want) <= self.doc["ulp"] * max(abs(want), 1e-300)

    def test_the_rows_hold_both_ways_for_every_law(self):
        self.assertTrue({"linear", "log"} <= set(self.doc["laws"]))
        for name, law in self.doc["laws"].items():
            travel = law["travel"]
            t = pg.Travel(travel)
            for row in law["rows"]:
                with self.subTest(law=name, value=row["value"]):
                    self.assertTrue(self.near(t.position(row["value"]), row["p"]), f"position {t.position(row['value'])} vs {row['p']}")
                    self.assertTrue(self.near(t.value(row["p"]), row.get("valueAtP", row["value"])), f"value {t.value(row['p'])}")


if __name__ == "__main__":
    unittest.main()
