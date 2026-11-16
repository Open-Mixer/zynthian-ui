# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: one gesture vocabulary of a panel's controls (zynthian_panel_gestures)
#
# omx-panel declares the gestures of every surface once, in schema/gestures.json (its docs/panel-gestures.md): the
# timings, the thresholds and a table of what each input means to each kind of control. This module maps Zynthian's
# pointer, wheel, encoder and key inputs onto that table and moves a control in the control's OWN unit and taper
# (the position law of zynthian_position_law), reading every number from the declaration. It keeps no timing, no
# threshold and no table of its own: without the installed omx-panel (or the file ZYNTHIAN_OMX_GESTURES names) it
# refuses, it does not fall back to a copy.
#
# Zynthian takes every word. A bar is a column of a BarGroup: the drawbar widget (zynthian_widget_drawbar, setBfree's
# and any LV2 organ's drawbars) drags in the pressed column and paints across the others (`paint`, a sweep). An xy is
# the XY screen (zynthian_gui_control_xy): two controllers on one surface, by XY. A handle is a one-value control read
# from the table by its key. `second`, a
# handle's Q, is taken where a row is given the controller that is its Q (Panel's `seconds`): by encoder 3, by
# Shift with the arrows, by the wheel and by a pinch of two touches (zynthian_touch_layer gives the second finger).
#
# Time is given by the caller (a Tk event's time, a script's timestamp), so a gesture is the same on the Pi and in
# a test.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import json
import math
import os
import shutil

from zyngine import zynthian_position_law as law

ENV_TABLE = "ZYNTHIAN_OMX_GESTURES"


class GestureTableAbsent(OSError):
    """The omx-panel installed here carries no schema/gestures.json."""


def table_path():
    """The declaration: the file ZYNTHIAN_OMX_GESTURES names, else schema/gestures.json beside the installed omx-panel."""
    named = os.environ.get(ENV_TABLE)
    if named:
        return named
    panel = shutil.which("omx-panel")
    if panel:
        here = os.path.dirname(os.path.realpath(panel))
        for _ in range(6):
            for sub in ("schema", os.path.join("dist", "schema")):
                p = os.path.join(here, sub, "gestures.json")
                if os.path.isfile(p):
                    return p
            here = os.path.dirname(here)
    raise GestureTableAbsent("omx-panel's schema/gestures.json is not installed: no gestures (no copy of the table is kept)")


_loaded = {}


def load_table(path=None):
    """The declaration, read once per file and modification time."""
    path = path or table_path()
    key = (path, os.stat(path).st_mtime_ns)
    if key not in _loaded:
        with open(path) as f:
            _loaded[key] = json.load(f)
    return _loaded[key]


# ---- A control's travel, in its own unit ------------------------------------------------------------------------


class Travel:
    """Where a value sits on its travel (0..1) and back, by the position law; the declared default; the declared step."""

    def __init__(self, travel, default=None, ticks=None, thresholds=None):
        self.travel = dict(travel)
        self.default = default
        self.ticks = list(ticks) if ticks else None
        self.stepped = self.ticks is not None or travel.get("scale") == "stepped"
        self.fraction = (thresholds or load_table()["thresholds"])["stepFraction"]  # the declaration's, never a default here

    @classmethod
    def of(cls, zctrl, thresholds=None):
        """A plugin-hostd controller's travel; any other controller's own range, linear."""
        if zctrl.ticks:
            return cls({"scale": "stepped", "min": 0, "max": len(zctrl.ticks) - 1, "step": 1},
                       zctrl.value_default, zctrl.ticks, thresholds)
        if zctrl.is_toggle:
            return cls({"scale": "stepped", "min": zctrl.value_min, "max": zctrl.value_max, "step": zctrl.value_max - zctrl.value_min},
                       zctrl.value_default, None, thresholds)
        t = dict(zctrl.position_law) if zctrl.position_law else {"scale": "linear"}
        t.update(min=zctrl.value_min, max=zctrl.value_max)
        if zctrl.is_integer and t["scale"] == "linear":
            t.update(scale="stepped", step=1)
        return cls(t, zctrl.value_default, None, thresholds)

    # the value of the ticked travel is an index
    def position(self, value):
        if self.ticks:
            value = self.ticks.index(value) if value in self.ticks else self.nearest(value)
        return min(1.0, max(0.0, law.scale_position(self.travel, value)))

    def nearest(self, value):
        return min(range(len(self.ticks)), key=lambda i: abs(self.ticks[i] - value))

    def value(self, pos):
        v = law.scale_value(self.travel, min(1.0, max(0.0, pos)))
        if self.ticks:
            return self.ticks[int(v)]
        if self.travel.get("scale") == "stepped" and float(v).is_integer() and float(self.travel.get("step", 0.5)).is_integer():
            return int(v)
        return v

    def step_norm(self):
        """One declared step on the 0..1 travel: a stepped travel's, a linear travel's declared step, else 1% of the travel."""
        t = self.travel
        if self.stepped:
            n = round((t["max"] - t["min"]) / t["step"]) + 1
            return 1.0 / (n - 1)
        if t.get("step") and t.get("scale", "linear") == "linear":
            return t["step"] / (t["max"] - t["min"])
        return self.fraction

    def step_of(self, value):
        """One declared step in the control's unit at `value`: the tolerance of the proof."""
        p = self.position(value)
        return abs(law.scale_value(self.travel, min(1.0, p + self.step_norm())) - law.scale_value(self.travel, p)) if not self.ticks else 1


# ---- The gestures of one control --------------------------------------------------------------------------------


class Gestures:
    """The gestures of one control: `widget` is the table's key (knob, fader, switch, selector), `travel` a Travel,
    `get` returns the control's value, `put(value)` moves it, and the three words that move nothing are told to
    `on_word(word)`: select, more. Inputs carry their time in ms."""

    def __init__(self, widget, travel, get, put, target, orientation="vertical", travel_px=None,
                 on_word=None, readonly=False, table=None, second=None):
        self.table = table or load_table()
        self.widget, self.travel, self.get, self.put = widget, travel, get, put
        self.target = target  # (x, y, w, h)
        self.horizontal = orientation == "horizontal"
        self.travel_px = travel_px
        self.on_word = on_word or (lambda word: None)
        self.readonly = readonly or not self.table["table"].get(widget)
        self.log = []  # every gesture: {word, input, begin, end, changes}
        self.refused = []
        self.owner = None  # {id, ptype, t0, x0, y0, x, y, dragging, fired}
        self.claim = None  # {source, until}
        self.last_tap = None
        self.step_gesture = None
        self.second = second  # (Travel, get, put) of the handle's Q, else None: `second` then has no surface
        self.pointers = {}  # id => {x0, y0, x, y, t0, ptype}: every pointer of the gesture
        self.pinch = None  # {a, b, d0, q0, g}

    # -- helpers

    def word(self, inp):
        return self.table["table"].get(self.widget, {}).get(inp)

    def refuse(self, code, t, why):
        self.refused.append({"code": code, "t": t, "why": why})

    def open(self, word, inp, t):
        g = {"word": word, "input": inp, "begin": t, "end": t, "changes": []}
        self.log.append(g)
        return g

    def change(self, g, value):
        g["changes"].append(value)
        self.put(value)

    def inside(self, x, y):
        tx, ty, tw, th = self.target
        return tx <= x < tx + tw and ty <= y < ty + th

    def tick(self, t):
        """A press held the long-press time without a drag is `more`."""
        o = self.owner
        T = self.table["timings"]
        if o and not o["dragging"] and not o["fired"] and t - o["t0"] >= T["longPressMs"]["default"]:
            o["fired"] = True
            if self.word("longPress") == "more":
                g = self.open("more", "longPress", o["t0"] + T["longPressMs"]["default"])
                self.on_word("more")
                return g

    # -- the pointer

    def press(self, x, y, t, pid="p", ptype="mouse"):
        self.tick(t)
        if not self.inside(x, y):
            return
        if self.readonly:
            return self.refuse("GESTURE_READ_ONLY", t, f"a {self.widget} that is read-only takes no gesture")
        if self.owner and pid != self.owner["id"] and pid not in self.pointers:
            return self.press_second(x, y, t, pid, ptype)
        if (self.claim and t < self.claim["until"]) or self.owner:
            return self.refuse("GESTURE_CONTROL_OWNED", t, "the control belongs to another input")
        T = self.table["timings"]
        second = self.last_tap is not None and self.last_tap["ptype"] == ptype and t - self.last_tap["t"] <= T["doubleTapMs"]["default"]
        self.owner = {"id": pid, "ptype": ptype, "t0": t, "x0": x, "y0": y, "x": x, "y": y, "dragging": False,
                      "fired": False, "second": second}
        self.pointers = {pid: {"x0": x, "y0": y, "x": x, "y": y, "t0": t, "ptype": ptype}}

    def press_second(self, x, y, t, pid, ptype):
        """A later press while one holds the control: a pinch when the table gives this control one, the two pointers are of
        one type, the first began inside the target and this one begins within the palm guard of it; else owned."""
        o = self.owner
        first = self.pointers.get(o["id"])
        T = self.table["timings"]
        if not (self.word("pinch") == "second" and self.second and not self.pinch and ptype == o["ptype"]
                and t - o["t0"] <= T["palmGuardMs"]["default"] and first and self.inside(first["x0"], first["y0"])):
            return self.refuse("GESTURE_CONTROL_OWNED", t, "the control belongs to another input")
        d0 = math.hypot(x - first["x"], y - first["y"]) or 1.0
        o["dragging"] = o["fired"] = True  # the first finger no longer drags or taps
        self.pointers[pid] = {"x0": x, "y0": y, "x": x, "y": y, "t0": t, "ptype": ptype}
        q = self.second[1]()
        self.pinch = {"a": o["id"], "b": pid, "d0": d0, "q0": q, "g": self.open("second", "pinch", t)}

    def pinch_move(self, t):
        """The spread of the two pointers scales Q, kept in the Q's own range."""
        a, b = self.pointers[self.pinch["a"]], self.pointers[self.pinch["b"]]
        q = self.second[0].travel
        scaled = min(q["max"], max(q["min"], self.pinch["q0"] * (math.hypot(a["x"] - b["x"], a["y"] - b["y"]) / self.pinch["d0"])))
        self.pinch["g"]["changes"].append(scaled)
        self.second[2](scaled)
        self.pinch["g"]["end"] = t

    def motion(self, x, y, t, pid="p", fine=False):
        self.tick(t)
        o = self.owner
        if self.pinch and pid in self.pointers:
            self.pointers[pid].update(x=x, y=y)
            return self.pinch_move(t)
        if not o or o["id"] != pid:
            return
        o["x"], o["y"] = x, y
        self.pointers[pid].update(x=x, y=y)
        G = self.table["thresholds"]
        if not o["dragging"]:
            if math.hypot(x - o["x0"], y - o["y0"]) <= G["dragStartPx"]:
                return
            if not self.word("drag"):
                return
            o["dragging"] = o["fired"] = True
            o["acc"] = self.travel.position(self.get())
            o["g"] = self.open("fine" if fine else "drag", "dragFine" if fine else "drag", o["t0"])
            o["px"], o["py"] = x, y  # the threshold is dead travel: the value moves from here
        ratio = G["fineRatio"] if fine else 1
        if fine:
            o["g"].update(word="fine", input="dragFine")
        dx, dy = x - o["px"], y - o["py"]
        o["px"], o["py"] = x, y
        px = self.travel_px or G["defaultTravelPx"]
        o["acc"] += ((dx if self.horizontal else -dy) / px) * ratio
        self.change(o["g"], self.travel.value(o["acc"]))
        o["g"]["end"] = t

    def release(self, x, y, t, pid="p"):
        self.tick(t)
        o = self.owner
        if self.pinch and pid in self.pointers:
            self.pointers.pop(pid)
            self.pinch["g"]["end"] = t
            self.pinch = None
            if len(self.pointers) <= 1:
                self.owner, self.pointers = None, {}  # the finger left does not carry on as a drag
            return
        if not o or o["id"] != pid:
            return
        self.owner = None
        self.pointers = {}
        if o["dragging"]:
            o["g"]["end"] = t
            return
        if o["fired"]:
            return
        if not self.inside(x, y):
            return  # a release outside the target is nothing
        if o["second"] and self.word("doubleTap") == "reset":
            g = self.open("reset", "doubleTap", o["t0"])
            self.last_tap = None
            g["end"] = t
            return self.reset(g, t)
        word = self.word("tap")
        if not word:
            return self.refuse("GESTURE_NOT_IN_TABLE", t, f"a {self.widget} has no tap")
        g = self.open(word, "tap", o["t0"])
        if word == "toggle":
            lo, hi = self.travel.travel["min"], self.travel.travel["max"]
            self.change(g, lo if self.get() == hi else hi)
        elif word == "select":
            self.on_word("select")  # a tap selects and never changes a value
        g["end"] = t
        self.last_tap = {"t": t, "ptype": o["ptype"]}

    # -- wheel, encoder, key

    def reset(self, g, t):
        if self.travel.default is None:
            self.log.pop()
            return self.refuse("GESTURE_NO_DEFAULT", t, "the control declares no default")
        self.change(g, self.travel.default)  # the declared default itself, exact

    def step(self, n, t, coarse=False, source="wheel"):
        """A wheel notch (n = +1 / -1), an encoder detent or an arrow key: one step; coarse is five."""
        self.tick(t)
        if source == "key" and coarse and self.widget == "handle":
            coarse, source = False, "arrowSecond"  # Shift with the arrows is the handle's Q
        inp = "arrowSecond" if source == "arrowSecond" else "encoder3" if source == "encoder3" else ("detentCoarse" if coarse else "detent") if source == "detent" else ("wheelCoarse" if coarse else "wheel") if source == "wheel" else ("arrowCoarse" if coarse else "arrow")
        if self.readonly:
            return self.refuse("GESTURE_READ_ONLY", t, f"a {self.widget} that is read-only takes no gesture")
        if self.owner or (self.claim and t < self.claim["until"] and self.claim["source"] != source):
            return self.refuse("GESTURE_CONTROL_OWNED", t, "the control belongs to another input")
        word = self.word(inp)
        if not word:
            return self.refuse("GESTURE_NOT_IN_TABLE", t, f"a {self.widget} has no {inp}")
        if word == "second" and self.second is None or word not in ("step", "second"):
            return self.refuse("GESTURE_NOT_TAKEN", t, f"the {word} of a {self.widget} has no surface here")  # no Q
        G = self.table["thresholds"]
        T = self.table["timings"]
        travel, get, put = (self.second if word == "second" else (self.travel, self.get, self.put))
        count = abs(n) * (G["coarseSteps"] if coarse else 1)
        # steps of one source within the claim are one gesture
        if not (self.step_gesture and self.claim and self.claim["source"] == source and t < self.claim["until"]):
            self.step_gesture = self.open(word, inp, t)
        pos = travel.position(get()) + (1 if n > 0 else -1) * count * travel.step_norm()
        self.step_gesture["changes"].append(travel.value(pos))
        put(travel.value(pos))
        self.claim = {"source": source, "until": t + T["claimMs"]["default"]}
        self.step_gesture["end"] = t

    def key(self, name, t, shift=False):
        self.tick(t)
        if name == "BackSpace" or name == "Backspace":
            if self.readonly:
                return self.refuse("GESTURE_READ_ONLY", t, "read-only")
            if self.word("backspace") == "reset":
                return self.reset(self.open("reset", "backspace", t), t)
            return self.refuse("GESTURE_NOT_IN_TABLE", t, f"a {self.widget} has no backspace")
        sign = {"Up": 1, "Right": 1, "Down": -1, "Left": -1}.get(name.replace("Arrow", ""))
        if sign:
            self.step(sign, t, coarse=shift, source="key")

    def shown(self, t):
        """Whether the control shows its value text: from press to release and through the claim after a step."""
        return self.owner is not None or bool(self.claim and t < self.claim["until"])


# ---- A bar group: one bar per column, a drag in the column, a sweep across them -----------------------------------


class BarGroup:
    """Bars side by side (an organ's drawbars): each column is a `bar` of the table, with its Travel, get, put and target
    (x, y, w, h). A drag in the pressed column moves it over the column's height; a drag that leaves the column paints:
    the pressed bar keeps the height it had in its column and every column entered takes the height under the pointer,
    absolute, a column jumped over in one event taking the line between (omx-panel's tools/gestures.mjs). A tap is
    `select` of its column, `more` a long press, a double-tap or Backspace the column's reset, a wheel or an arrow a step
    of the selected column. `downward`: the bars come out downward (their value grows down the column), as the drawbar
    widget draws them. `on_word(word, column)`."""

    def __init__(self, bars, on_word=None, downward=False, table=None):
        self.table = table or load_table()
        self.on_word = on_word or (lambda word, column=None: None)
        self.downward = downward
        self.bars = []
        for i, (travel, get, put, target) in enumerate(bars):
            g = Gestures("bar", travel, get, put, target, travel_px=target[3], table=self.table,
                         on_word=lambda word, i=i: self.on_word(word, i))
            if downward:
                g.horizontal = False
                g.motion = self._downward(g)
            self.bars.append(g)
        self.log = []  # the gestures of every column, in order
        self.pressed = None  # {col, pid, in_y, painting, prev}
        self.selected = 0

    @staticmethod
    def _downward(g):
        """A bar whose value grows down its column: the column's drag with y turned over."""
        plain = Gestures.motion.__get__(g)
        tx, ty, tw, th = g.target

        def motion(x, y, t, pid="p", fine=False):
            o = g.owner
            if o and "flip0" not in o:
                o["flip0"] = True
                o["y0"] = 2 * ty + th - o["y0"]
            return plain(x, 2 * ty + th - y, t, pid, fine)
        return motion

    def column(self, x, y=None):
        for i, g in enumerate(self.bars):
            tx, ty, tw, th = g.target
            if tx <= x < tx + tw and (y is None or ty <= y < ty + th):
                return i
        return None

    def height_at(self, i, y):
        g = self.bars[i]
        tx, ty, tw, th = g.target
        n = (y - ty) / th if self.downward else (ty + th - y) / th
        return g.travel.value(min(1.0, max(0.0, n)))

    def _logged(self, g, before):
        for entry in g.log[before:]:
            self.log.append(entry)

    def press(self, x, y, t, pid="p", ptype="mouse"):
        i = self.column(x, y)
        if i is None:
            return
        g = self.bars[i]
        n = len(g.log)
        g.press(x, y, t, pid, ptype)
        self._logged(g, n)
        if g.owner and g.owner["id"] == pid:
            self.pressed = {"col": i, "pid": pid, "in_x": x, "in_y": y, "painting": False, "prev": (x, y)}

    def motion(self, x, y, t, pid="p", fine=False):
        p = self.pressed
        if not p or p["pid"] != pid:
            return
        g = self.bars[p["col"]]
        col = self.column(x)
        if not p["painting"] and col == p["col"]:
            p["in_x"], p["in_y"] = x, y
        if not p["painting"]:
            n = len(g.log)
            if col == p["col"] or col is None or not (g.owner and g.owner["dragging"]):
                g.motion(x, y, t, pid, fine)
                self._logged(g, n)
                if col == p["col"] or col is None or not (g.owner and g.owner["dragging"]):
                    return
            # the drag left the pressed column: it paints from here, one gesture
            p["painting"] = True
            gesture = g.owner["g"]
            gesture.update(word="paint", input="sweep")
            v = self.height_at(p["col"], p["in_y"])
            gesture["changes"].append(v)
            g.put(v)
            p["prev"] = (p["in_x"], p["in_y"])
            p["g"] = gesture
        if col is None:
            return
        px, py = p["prev"]
        frm = self.column(px)
        step = (col > frm) - (col < frm)
        entered = [col] if step == 0 else [frm + step * (k + 1) for k in range(abs(col - frm))]
        for c in entered:
            b = self.bars[c]
            cx = b.target[0] + b.target[2] / 2
            yy = y if c == col else py + (y - py) * ((cx - px) / ((x - px) or 1))
            v = self.height_at(c, yy)
            p["g"]["changes"].append(v)
            b.put(v)
        p["prev"] = (x, y)
        p["g"]["end"] = t

    def release(self, x, y, t, pid="p"):
        p = self.pressed
        if not p or p["pid"] != pid:
            return
        self.pressed = None
        g = self.bars[p["col"]]
        if p["painting"]:
            p["g"]["end"] = t
            g.owner, g.pointers = None, {}
            return
        n = len(g.log)
        g.release(x, y, t, pid)
        self._logged(g, n)
        if g.log[n:] and g.log[-1]["word"] == "select":
            self.selected = p["col"]

    def tick(self, t):
        for g in self.bars:
            n = len(g.log)
            g.tick(t)
            self._logged(g, n)

    def step(self, n, t, coarse=False, source="wheel"):
        g = self.bars[self.selected]
        k = len(g.log)
        g.step(-n if self.downward else n, t, coarse, source)
        self._logged(g, k)

    def key(self, name, t, shift=False):
        if name.replace("Arrow", "") in ("Left", "Right"):
            self.selected = min(len(self.bars) - 1, max(0, self.selected + (1 if "Right" in name else -1)))
            return
        g = self.bars[self.selected]
        k = len(g.log)
        if self.downward and name.replace("Arrow", "") in ("Up", "Down"):
            name = "Down" if "Up" in name else "Up"
        g.key(name, t, shift)
        self._logged(g, k)


# ---- An xy: two travels on one surface ---------------------------------------------------------------------------


class XY:
    """A two-dimensional control (`xy` of the table): `tx`, `ty` the Travels of its two axes, `get()` -> (x, y), `put(x, y)`,
    `target` (x, y, w, h). A drag moves both axes from where the threshold was crossed, over the target's width and
    height (y grows downward, as the screen draws it), `fine` by the declared ratio; a tap is `select`, a long press
    `more`, a double-tap or Backspace resets both axes to their declared defaults; Left and Right step x, Down and Up
    step y, Down growing it as the screen draws it (Shift: coarse)."""

    def __init__(self, tx, ty, get, put, target, on_word=None, table=None):
        self.table = table or load_table()
        self.tx, self.ty, self.get, self.put, self.target = tx, ty, get, put, target
        self.on_word = on_word or (lambda word: None)
        self.log, self.refused = [], []
        self.owner, self.last_tap, self.claim, self.step_gesture = None, None, None, None

    def word(self, inp):
        return self.table["table"]["xy"].get(inp)

    def open(self, word, inp, t):
        g = {"word": word, "input": inp, "begin": t, "end": t, "changes": []}
        self.log.append(g)
        return g

    def _put(self, g, xv, yv):
        g["changes"].append((xv, yv))
        self.put(xv, yv)

    def inside(self, x, y):
        tx, ty, tw, th = self.target
        return tx <= x < tx + tw and ty <= y < ty + th

    def tick(self, t):
        o = self.owner
        T = self.table["timings"]
        if o and not o["dragging"] and not o["fired"] and t - o["t0"] >= T["longPressMs"]["default"]:
            o["fired"] = True
            if self.word("longPress") == "more":
                self.open("more", "longPress", o["t0"] + T["longPressMs"]["default"])
                self.on_word("more")

    def press(self, x, y, t, pid="p", ptype="mouse"):
        self.tick(t)
        if not self.inside(x, y):
            return
        if self.owner:
            self.refused.append({"code": "GESTURE_CONTROL_OWNED", "t": t, "why": "the control belongs to another input"})
            return
        T = self.table["timings"]
        second = self.last_tap is not None and self.last_tap["ptype"] == ptype and t - self.last_tap["t"] <= T["doubleTapMs"]["default"]
        self.owner = {"id": pid, "ptype": ptype, "t0": t, "x0": x, "y0": y, "dragging": False, "fired": False, "second": second}

    def motion(self, x, y, t, pid="p", fine=False):
        self.tick(t)
        o = self.owner
        if not o or o["id"] != pid:
            return
        G = self.table["thresholds"]
        if not o["dragging"]:
            if math.hypot(x - o["x0"], y - o["y0"]) <= G["dragStartPx"]:
                return
            xv, yv = self.get()
            o.update(dragging=True, fired=True, ax=self.tx.position(xv), ay=self.ty.position(yv), px=x, py=y,
                     g=self.open("fine" if fine else "drag", "dragFine" if fine else "drag", o["t0"]))
        if fine:
            o["g"].update(word="fine", input="dragFine")
        ratio = G["fineRatio"] if fine else 1
        _, _, tw, th = self.target
        o["ax"] += (x - o["px"]) / tw * ratio
        o["ay"] += (y - o["py"]) / th * ratio
        o["px"], o["py"] = x, y
        self._put(o["g"], self.tx.value(o["ax"]), self.ty.value(o["ay"]))
        o["g"]["end"] = t

    def release(self, x, y, t, pid="p"):
        self.tick(t)
        o = self.owner
        if not o or o["id"] != pid:
            return
        self.owner = None
        if o["dragging"]:
            o["g"]["end"] = t
            return
        if o["fired"] or not self.inside(x, y):
            return
        if o["second"] and self.word("doubleTap") == "reset":
            self.last_tap = None
            return self.reset(self.open("reset", "doubleTap", o["t0"]), t)
        g = self.open(self.word("tap"), "tap", o["t0"])
        g["end"] = t
        self.on_word("select")  # a tap selects and never changes a value
        self.last_tap = {"t": t, "ptype": o["ptype"]}

    def reset(self, g, t):
        if self.tx.default is None or self.ty.default is None:
            self.log.pop()
            self.refused.append({"code": "GESTURE_NO_DEFAULT", "t": t, "why": "an axis declares no default"})
            return
        self._put(g, self.tx.default, self.ty.default)
        g["end"] = t

    def key(self, name, t, shift=False):
        self.tick(t)
        if name in ("BackSpace", "Backspace"):
            return self.reset(self.open("reset", "backspace", t), t)
        name = name.replace("Arrow", "")
        if name not in ("Up", "Down", "Left", "Right") or self.owner:
            return
        inp = "arrowCoarse" if shift else "arrow"
        if self.word(inp) != "step":
            return
        G, T = self.table["thresholds"], self.table["timings"]
        count = G["coarseSteps"] if shift else 1
        xv, yv = self.get()
        if not (self.step_gesture and self.claim and t < self.claim["until"]):
            self.step_gesture = self.open("step", inp, t)
        if name in ("Left", "Right"):
            xv = self.tx.value(self.tx.position(xv) + (1 if name == "Right" else -1) * count * self.tx.step_norm())
        else:
            yv = self.ty.value(self.ty.position(yv) + (1 if name == "Down" else -1) * count * self.ty.step_norm())  # y grows downward
        self._put(self.step_gesture, xv, yv)
        self.claim = {"until": t + T["claimMs"]["default"]}
        self.step_gesture["end"] = t


# ---- Tk's events onto the inputs ---------------------------------------------------------------------------------

SHIFT = 0x1


def tk_press(gestures, e):
    gestures.press(e.x, e.y, e.time, "mouse1", "mouse")


def tk_motion(gestures, e):
    gestures.motion(e.x, e.y, e.time, "mouse1", fine=bool(e.state & SHIFT))


def tk_release(gestures, e):
    gestures.release(e.x, e.y, e.time, "mouse1")


def tk_wheel(gestures, e):
    """X11 wheel is buttons 4 and 5; elsewhere delta's sign. Shift is the coarse step."""
    up = getattr(e, "num", None) == 4 or (getattr(e, "delta", 0) or 0) > 0
    gestures.step(1 if up else -1, e.time, coarse=bool(e.state & SHIFT), source="wheel")


def tk_key(gestures, e):
    gestures.key(e.keysym, e.time, shift=bool(e.state & SHIFT))


# ---- A page of controls: one row each, the pointer routed to the row it pressed ---------------------------------


def widget_of(zctrl):
    """The table's key of a controller: a toggle is a switch, one with labels a selector, the rest a fader."""
    if zctrl.is_toggle:
        return "switch"
    return "selector" if zctrl.ticks else "fader"


class Panel:
    """The rows of a page. A row is a horizontal strip of the canvas, `margin` px in from each side, whose drawn length is
    the travel of its drag; a press belongs to the row it lands in, and the motion and the release follow that row."""

    def __init__(self, zctrls, width, height, margin, table=None, on_word=None, seconds=None):
        self.table = table or load_table()
        self.rows = []
        self.on_word = on_word or (lambda zctrl, word: None)
        self.pressed = None
        n = max(1, len(zctrls))
        for i, zctrl in enumerate(zctrls):
            travel = Travel.of(zctrl, self.table["thresholds"])
            q = (seconds or {}).get(zctrl.symbol)  # the controller that is this row's Q: the row is then a handle
            self.rows.append((zctrl, Gestures(
                "handle" if q is not None else widget_of(zctrl), travel, lambda z=zctrl: z.value, lambda v, z=zctrl: z.set_value(v),
                (0, i * height / n, width, height / n), orientation="horizontal", travel_px=max(1, width - 2 * margin),
                on_word=lambda word, z=zctrl: self.on_word(z, word), readonly=bool(zctrl.readonly), table=self.table,
                second=None if q is None else (Travel.of(q, self.table["thresholds"]), lambda z=q: z.value, lambda v, z=q: z.set_value(v)))))

    def row_at(self, y):
        for zctrl, g in self.rows:
            if g.inside(0, y):
                return g

    def press(self, x, y, t, pid="mouse1", ptype="mouse"):
        if self.pressed and pid not in self.pressed.pointers and self.pressed.owner:
            return self.pressed.press(x, y, t, pid, ptype)  # a second finger belongs to the row the first holds
        self.pressed = self.row_at(y)
        if self.pressed:
            self.pressed.press(x, y, t, pid, ptype)

    def motion(self, x, y, t, pid="mouse1", fine=False):
        if self.pressed:
            self.pressed.motion(x, y, t, pid, fine)

    def release(self, x, y, t, pid="mouse1"):
        row = self.pressed
        if row:
            row.release(x, y, t, pid)
            if row.owner is None:
                self.pressed = None

    def tick(self, t):
        for _, g in self.rows:
            g.tick(t)
