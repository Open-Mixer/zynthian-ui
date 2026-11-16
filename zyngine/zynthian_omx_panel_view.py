#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Engine (zynthian_omx_panel_view)
#
# A plugin's panel drawn by omx-panel's renderer, the one C library every OpenMixer surface draws a panel with
# (libomx-panel-render.so.0, omx-panel's renderer/include/omx_panel_render.h): its bars, its curves and its meters,
# in the omx look. This module is the ctypes door to it, and the host's side the renderer leaves to the host: which
# part of the panel a screen shows, the curve_bind line plugin-hostd draws a display's points from, and the reply
# of curve_points. Nothing here draws or computes a point: the renderer draws, plugin-hostd computes (omx-dsp's
# omx_curve_points), and a missing library is said by name.
#
# The renderer runs in a process of its own (zynthian-ui#44): a fault inside it stops that process, never the UI's. The
# UI's View sends each call to it over a socket and reads the drawn pixels from shared memory; when the renderer
# stops, the call raises RendererStopped, saying how, and the next View starts it again. This file is that process
# too (run as `python3 zynthian_omx_panel_view.py --serve <fd>`): it imports nothing but the standard library.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import ctypes
import json
import logging
import math
import os
import signal
import socket
import subprocess
import sys
import tempfile
from multiprocessing import connection, shared_memory

LIBRARY = "libomx-panel-render.so.0"
# the look, the geometry and the font a view is made from: omx-panel's tools directory as the package installs it
TOOLS_DIR = "/usr/share/omx-panel/tools"

PIXEL_RGBA8_STRAIGHT = 2

# omx_panel_event_kind_t, omx_panel_key_t, omx_panel_pointer_t; the gesture words (omx_panel_word_t) are not listed
# here: word_name() asks the library for the name of the one an answer carries
EVENT_DOWN, EVENT_MOVE, EVENT_UP, EVENT_WHEEL, EVENT_DETENT, EVENT_KEY = range(6)
KEY_BACKSPACE, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT = range(5)
POINTER_TOUCH, POINTER_MOUSE = 0, 1


class RendererAbsent(Exception):
    """The renderer cannot be loaded or refuses the panel: the reason, said once by the caller."""


class RendererStopped(RendererAbsent):
    """The renderer's process stopped (a fault inside the library, or no answer): how, said once by the caller. The
    views it held are gone; the next View starts the renderer again."""


class _Buffer(ctypes.Structure):
    _fields_ = [("pixels", ctypes.c_void_p), ("width", ctypes.c_uint32), ("height", ctypes.c_uint32),
                ("stride", ctypes.c_uint32), ("scale", ctypes.c_double), ("format", ctypes.c_int)]


class _Event(ctypes.Structure):
    _fields_ = [("t_ms", ctypes.c_double), ("kind", ctypes.c_int), ("pointer", ctypes.c_uint32), ("type", ctypes.c_int),
                ("x", ctypes.c_double), ("y", ctypes.c_double), ("fine", ctypes.c_bool), ("n", ctypes.c_int32),
                ("coarse", ctypes.c_bool), ("encoder", ctypes.c_int32), ("key", ctypes.c_int), ("shift", ctypes.c_bool),
                ("control", ctypes.c_int32)]


class _Change(ctypes.Structure):
    _fields_ = [("control", ctypes.c_uint32), ("fraction", ctypes.c_double), ("value", ctypes.c_double)]


class _Answer(ctypes.Structure):
    _fields_ = [("word", ctypes.c_int), ("gesture", ctypes.c_uint32), ("begin_ms", ctypes.c_double),
                ("end_ms", ctypes.c_double), ("shown_until_ms", ctypes.c_double), ("ended", ctypes.c_bool),
                ("undo", ctypes.c_bool), ("cancelled", ctypes.c_bool), ("refusal", ctypes.c_int),
                ("selected", ctypes.c_int32)]


class _Travel(ctypes.Structure):
    _fields_ = [("min", ctypes.c_double), ("max", ctypes.c_double), ("def", ctypes.c_double), ("step", ctypes.c_double),
                ("has_def", ctypes.c_bool), ("log", ctypes.c_bool), ("integer", ctypes.c_bool)]


_lib = None
_lib_error = None


def library():
    """The renderer, loaded once: $ZYNTHIAN_OMX_PANEL_RENDER names a file, else the soname. RendererAbsent says why not."""
    global _lib, _lib_error
    if _lib is None and _lib_error is None:
        name = os.environ.get("ZYNTHIAN_OMX_PANEL_RENDER", LIBRARY)
        try:
            lib = ctypes.CDLL(name)
        except OSError as e:
            _lib_error = f"omx-panel's renderer ({name}) is not installed: {e}"
        else:
            try:
                _declare(lib)
            except AttributeError as e:
                _lib_error = f"omx-panel's renderer ({name}) is older than this module needs: {e}"
            else:
                _lib = lib
    if _lib is None:
        raise RendererAbsent(_lib_error)
    return _lib


def _declare(lib):
    P, U, D, B, S = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_double, ctypes.c_bool, ctypes.c_char_p
    DP = ctypes.POINTER(ctypes.c_double)
    for name, res, args in (
            ("omx_panel_view_create_from_files", P, [S, S, ctypes.c_char_p, ctypes.c_size_t]),
            ("omx_panel_view_destroy", None, [P]),
            ("omx_panel_view_count", U, [P]),
            ("omx_panel_view_symbol", S, [P, U]),
            ("omx_panel_view_set_title", None, [P, S, S]),
            ("omx_panel_view_set_value", B, [P, U, D, S]),
            ("omx_panel_view_set_choice", B, [P, U, U, U, S]),
            ("omx_panel_view_set_meter", B, [P, U, D, D]),
            ("omx_panel_view_set_curve", B, [P, U, DP, DP, U]),
            ("omx_panel_view_natural_size", None, [P, ctypes.POINTER(U), ctypes.POINTER(U)]),
            ("omx_panel_view_draw", B, [P, ctypes.POINTER(_Buffer)]),
            ("omx_panel_view_set_surface", B, [P, U, U, D]),
            ("omx_panel_view_set_travel", B, [P, U, ctypes.POINTER(_Travel)]),
            ("omx_panel_view_input", ctypes.c_size_t, [P, ctypes.POINTER(_Event), ctypes.POINTER(_Change), ctypes.c_size_t,
                                                       ctypes.POINTER(_Answer)]),
            ("omx_panel_view_target_rect", B, [P, U, ctypes.POINTER(ctypes.c_double * 4), DP]),
            ("omx_panel_view_tick", ctypes.c_size_t, [P, D, ctypes.POINTER(_Change), ctypes.c_size_t,
                                                      ctypes.POINTER(_Answer)]),
            ("omx_panel_word_name", S, [ctypes.c_int])):
        f = getattr(lib, name)
        f.restype, f.argtypes = res, args


def _word_name(word):
    name = library().omx_panel_word_name(word)
    return None if name is None else name.decode()


def word_name(word):
    """The name of a gesture word as omx-panel's gestures.json spells it; "" for no word, None for a value that is none."""
    return _host().call("word", None, word)


class _LibraryView:
    """One panel layout (what `omx-panel describe --layout` prints, or a part of it) as the renderer holds it, in the
    process that loaded the library: the renderer's process."""

    def __init__(self, layout, tools_dir=None):
        lib = self.lib = library()
        self.layout = layout
        with tempfile.NamedTemporaryFile("w", suffix=".layout.json", delete=False) as f:
            json.dump(layout, f)
            path = f.name
        err = ctypes.create_string_buffer(512)
        try:
            tools = tools_dir or os.environ.get("ZYNTHIAN_OMX_PANEL_TOOLS", TOOLS_DIR)
            self.view = lib.omx_panel_view_create_from_files(path.encode(), tools.encode(), err, len(err))
        finally:
            os.unlink(path)
        if not self.view:
            raise RendererAbsent(f"omx-panel's renderer refused the panel: {err.value.decode(errors='replace')}")
        self.symbols = [lib.omx_panel_view_symbol(self.view, i).decode() for i in range(lib.omx_panel_view_count(self.view))]
        self.meters = [m["symbol"] for m in layout.get("meters") or []]
        self.size = None

    def close(self):
        if self.view:
            self.lib.omx_panel_view_destroy(self.view)
            self.view = None

    def __del__(self):
        self.close()

    def natural_size(self):
        w, h = ctypes.c_uint32(), ctypes.c_uint32()
        self.lib.omx_panel_view_natural_size(self.view, ctypes.byref(w), ctypes.byref(h))
        return w.value, h.value

    def set_title(self, brand, name):
        self.lib.omx_panel_view_set_title(self.view, (brand or "").encode(), (name or "").encode())

    def set_value(self, index, fraction, text):
        return self.lib.omx_panel_view_set_value(self.view, index, fraction, ("" if text is None else str(text)).encode())

    def set_choice(self, index, at, count, text):
        return self.lib.omx_panel_view_set_choice(self.view, index, at, count, ("" if text is None else str(text)).encode())

    def set_meter(self, index, value, elapsed):
        return self.lib.omx_panel_view_set_meter(self.view, index, value, elapsed)

    def set_curve(self, display, points):
        n = len(points)
        xs = (ctypes.c_double * n)(*(p[0] for p in points))
        ys = (ctypes.c_double * n)(*(p[1] for p in points))
        return self.lib.omx_panel_view_set_curve(self.view, display, xs, ys, n)

    def set_surface(self, width, height, scale=1.0):
        self.size = (width, height)
        return self.lib.omx_panel_view_set_surface(self.view, width, height, scale)

    def set_travel(self, index, lo, hi, default=None, step=0.0, log=False, integer=False):
        t = _Travel(lo, hi, default if default is not None else lo, step or 0.0, default is not None, log, integer)
        return self.lib.omx_panel_view_set_travel(self.view, index, ctypes.byref(t))

    def target_rect(self, index):
        """Where control `index` takes a press, (x, y, w, h) in the surface's px, and the px a drag over its whole
        travel covers; None for a hidden control or before set_surface."""
        rect, travel = (ctypes.c_double * 4)(), ctypes.c_double()
        if not self.lib.omx_panel_view_target_rect(self.view, index, ctypes.byref(rect), ctypes.byref(travel)):
            return None
        return tuple(rect), travel.value

    def input(self, kind, t_ms, x=0.0, y=0.0, pointer=1, ptype=POINTER_MOUSE, fine=False, n=0, coarse=False, key=0,
              shift=False, control=-1):
        """One event; (the changes as [(control index, fraction, value)], the answer's word, the selected control)."""
        e = _Event(t_ms, kind, pointer, ptype, x, y, fine, n, coarse, 0, key, shift, control)
        changes = (_Change * 64)()
        a = _Answer()
        k = self.lib.omx_panel_view_input(self.view, ctypes.byref(e), changes, 64, ctypes.byref(a))
        return [(c.control, c.fraction, c.value) for c in changes[:k]], _word_name(a.word), a.selected

    def tick(self, t_ms):
        changes = (_Change * 64)()
        a = _Answer()
        k = self.lib.omx_panel_view_tick(self.view, t_ms, changes, 64, ctypes.byref(a))
        return [(c.control, c.fraction, c.value) for c in changes[:k]], _word_name(a.word), a.selected

    def draw(self, width, height, scale=1.0):
        """The panel drawn into width x height pixels: RGBA, straight alpha, rows of width * 4 bytes."""
        pixels = ctypes.create_string_buffer(width * height * 4)
        buf = _Buffer(ctypes.cast(pixels, ctypes.c_void_p), width, height, width * 4, scale, PIXEL_RGBA8_STRAIGHT)
        if not self.lib.omx_panel_view_draw(self.view, ctypes.byref(buf)):
            raise RendererAbsent(f"omx-panel's renderer did not draw a {width} x {height} panel")
        return pixels.raw


# ---- The renderer's process ----

# a call answers within this, else the renderer is taken as stopped (a draw of the whole screen takes milliseconds)
ANSWER_S = 5.0

_the_host = None


def _attach(name):
    """The UI's shared memory, attached without the resource tracker taking it over (the UI owns it)."""
    return shared_memory.SharedMemory(name=name, track=False)


def _serve(fd):
    """The renderer's process: the views it holds by number, each call answered ("ok", value) or ("refused", why)."""
    conn = connection.Connection(fd)
    views, memory, next_id = {}, {}, 1
    while True:
        try:
            op, vid, args = conn.recv()
        except (EOFError, OSError):
            return
        try:
            if op == "open":
                v = _LibraryView(*args)
                views[next_id] = v
                value = (next_id, v.symbols)
                next_id += 1
            elif op == "close":
                v = views.pop(vid, None)
                if v:
                    v.close()
                value = None
            elif op == "word":
                value = _word_name(*args)
            elif op == "draw":
                name, width, height, scale = args
                pixels = views[vid].draw(width, height, scale)
                if name not in memory:
                    memory[name] = _attach(name)
                memory[name].buf[:len(pixels)] = pixels
                value = len(pixels)
            else:
                value = getattr(views[vid], op)(*args)
            conn.send(("ok", value))
        except Exception as e:  # the library's refusal, or a call it cannot take: said, the process goes on
            conn.send(("refused", str(e) if isinstance(e, RendererAbsent) else f"{op}: {e!r}"))


class _Host:
    """The renderer's process as the UI holds it: started on the first view, one for every view."""

    def __init__(self):
        ours, theirs = socket.socketpair()
        self.process = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--serve", str(theirs.fileno())],
                                        pass_fds=[theirs.fileno()], stdin=subprocess.DEVNULL)
        theirs.close()
        self.conn = connection.Connection(ours.detach())
        self.stopped = None

    def call(self, op, vid, *args):
        if self.stopped:
            raise RendererStopped(self.stopped)
        try:
            self.conn.send((op, vid, args))
            if not self.conn.poll(ANSWER_S):
                self.process.kill()
                raise EOFError(f"no answer in {ANSWER_S:g} s")
            kind, value = self.conn.recv()
        except (EOFError, OSError) as e:
            self.stop(e)
            raise RendererStopped(self.stopped) from None
        if kind == "refused":
            raise RendererAbsent(value)
        return value

    def stop(self, why):
        try:
            code = self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            code = self.process.wait()
        if code is not None and code < 0:
            try:
                how = signal.Signals(-code).name
            except ValueError:
                how = f"signal {-code}"
        else:
            how = f"exit {code}" if code else str(why)
        self.stopped = f"omx-panel's renderer stopped ({how}); the panel is drawn again when it is opened again"
        logging.error(self.stopped)
        self.conn.close()

    def alive(self):
        return not self.stopped and self.process.poll() is None


def _host():
    """The renderer's process, started again when the last one stopped."""
    global _the_host
    if _the_host is None or not _the_host.alive():
        _the_host = _Host()
    return _the_host


class View:
    """One panel layout (what `omx-panel describe --layout` prints, or a part of it) as the renderer holds it, in the
    renderer's process: each call is the library's, its answer the library's. RendererStopped when that process
    stopped."""

    def __init__(self, layout, tools_dir=None):
        self.host = _host()
        self.layout = layout
        self.id, self.symbols = self.host.call("open", None, layout, tools_dir)
        self.meters = [m["symbol"] for m in layout.get("meters") or []]
        self.size = None
        self.memory = None

    def _call(self, op, *args):
        return self.host.call(op, self.id, *args)

    def close(self):
        if self.id is not None and self.host.alive():
            try:
                self._call("close")
            except RendererAbsent:
                pass
        self.id = None
        if self.memory:
            self.memory.close()
            self.memory.unlink()
            self.memory = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def natural_size(self):
        return self._call("natural_size")

    def set_title(self, brand, name):
        self._call("set_title", brand, name)

    def set_value(self, index, fraction, text):
        return self._call("set_value", index, fraction, text)

    def set_choice(self, index, at, count, text):
        return self._call("set_choice", index, at, count, text)

    def set_meter(self, index, value, elapsed):
        return self._call("set_meter", index, value, elapsed)

    def set_curve(self, display, points):
        return self._call("set_curve", display, [tuple(p) for p in points])

    def set_surface(self, width, height, scale=1.0):
        self.size = (width, height)
        return self._call("set_surface", width, height, scale)

    def set_travel(self, index, lo, hi, default=None, step=0.0, log=False, integer=False):
        return self._call("set_travel", index, lo, hi, default, step, log, integer)

    def target_rect(self, index):
        """Where control `index` takes a press, (x, y, w, h) in the surface's px, and the px a drag over its whole
        travel covers; None for a hidden control or before set_surface."""
        return self._call("target_rect", index)

    def input(self, kind, t_ms, x=0.0, y=0.0, pointer=1, ptype=POINTER_MOUSE, fine=False, n=0, coarse=False, key=0,
              shift=False, control=-1):
        """One event; (the changes as [(control index, fraction, value)], the answer's word, the selected control)."""
        return self._call("input", kind, t_ms, x, y, pointer, ptype, fine, n, coarse, key, shift, control)

    def tick(self, t_ms):
        return self._call("tick", t_ms)

    def draw(self, width, height, scale=1.0):
        """The panel drawn into width x height pixels: RGBA, straight alpha, rows of width * 4 bytes."""
        size = width * height * 4
        if self.memory is None or self.memory.size < size:
            if self.memory:
                self.memory.close()
                self.memory.unlink()
            self.memory = shared_memory.SharedMemory(create=True, size=size)
        n = self._call("draw", self.memory.name, width, height, scale)
        return bytes(self.memory.buf[:n])


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
    lo, hi = 0, rows - top - 1  # rows below the band that match from the bottom, leaving the top row in
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


# ---- What a screen shows of the panel ----

def drawn_parts(layout):
    """Whether the layout has anything the plain controller screens cannot show: a bar group, a display or a meter."""
    return bool(layout.get("displays") or layout.get("meters") or any(s.get("bars") for s in layout.get("sections", [])))


def screen_part(layout, keys):
    """The part of `layout` a screen shows for the controls `keys` (layout symbols) on it: their sections with
    every control, a display's section above them (a curve stays on every page of its panel), and the meters.
    Indices are renumbered; returns (part, {the part's display index: the layout's display index})."""
    sections = layout.get("sections", [])
    controls = layout.get("controls", [])
    displays = layout.get("displays", [])
    wanted = {c["section"] for c in controls if c["symbol"] in keys}
    wanted |= {d["section"] for d in displays if d.get("kind") in curve_words()[0]}
    order = [i for i in range(len(sections)) if i in wanted]
    new = {old: k for k, old in enumerate(order)}
    part = dict(layout)
    part["sections"] = [sections[i] for i in order]
    part["controls"] = [dict(c, section=new[c["section"]]) for c in controls if c["section"] in new]
    kept = [(i, d) for i, d in enumerate(displays) if d.get("section") in new]
    part["displays"] = [dict(d, section=new[d["section"]]) for _, d in kept]
    return part, {k: i for k, (i, _) in enumerate(kept)}


# ---- The curve a display draws: plugin-hostd computes it from a binding (protocol 0.5, curve_bind / curve_points) ----

CONTRACT_PATH = "/usr/share/omx-contract/contract.d"
_curve_words = {}  # contract directory => (display kinds, role words)


def curve_words(root=None):
    """(the display kinds drawn from a curve, the role words a curve is bound by) as omx-dsp declares them:
    CURVE_DISPLAYS and CURVE_ROLES of the curve.json its contract package installs, in the wire's spelling (snake
    case, the description's own words). A role of the description that is none of these (attack, release, mix) draws
    nothing and is not bound. Two empty tuples when the declaration cannot be read: no display is a curve then."""
    root = root or (os.environ.get("OMX_CONTRACT_PATH") or CONTRACT_PATH).split(":")[0]
    if root not in _curve_words:
        def wire(ids):
            return tuple("".join("_" + c.lower() if c.isupper() else c for c in i) for i in ids)
        try:
            with open(os.path.join(root, "3", "omx-dsp", "primitives", "curve.json")) as f:
                doc = json.load(f)
            _curve_words[root] = wire(doc["CURVE_DISPLAYS"]["ids"]), wire(doc["CURVE_ROLES"]["ids"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            logging.warning("omx-dsp's curve.json is not readable (%s): no curve is drawn", e)
            return (), ()
    return _curve_words[root]


def curve_bind_line(instance, index, description):
    """The curve_bind line of display `index` of a description (`omx-panel describe`'s): its kind, the family and a
    term per role, <role>[.<index>]=<symbol>:<unit>[@<shape>|...], the symbols as the daemon sets them. None for a
    display that is not a curve."""
    display = (description.get("displays") or [])[index]
    kinds, roles = curve_words()
    if display.get("kind") not in kinds:
        return None
    terms = []
    for r in description.get("roles", []):
        if r["role"] not in roles:
            continue
        role = r["role"] + (f".{r['index']}" if r["role"].startswith("band_") else "")
        term = f"{role}={r['symbol']}:{r.get('unit') or 'none'}"
        if r.get("shapes"):
            term += "@" + "|".join(r["shapes"])
        elif r.get("shape"):
            term += "@" + r["shape"]
        terms.append(term)
    return " ".join([f"curve_bind {instance} {index} {display['kind']} {description.get('family')}"] + terms)


def curve_points(reply):
    """The points of a curve_points reply ('<count> <x>,<y> ...'), ascending in x; [] for a reply that is not one."""
    words = reply.split()
    try:
        n = int(words[0])
        points = [tuple(float(v) for v in w.split(",")) for w in words[1:n + 1]]
    except (IndexError, ValueError):
        return []
    if len(points) != n or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        return []
    return points


def output_set(line):
    """A feedback line 'output_set <instance> <symbol> <value>' as (instance, symbol, value); None for any other."""
    words = line.split()
    if len(words) != 4 or words[0] != "output_set":
        return None
    try:
        return int(words[1]), words[2], float(words[3])
    except ValueError:
        return None


if __name__ == "__main__" and sys.argv[1:2] == ["--serve"]:
    _serve(int(sys.argv[2]))
