#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Engine (zynthian_omx_panel_view)
#
# A plugin's panel drawn by omx-panel's renderer, omx-panel's own C library for drawing a panel
# (libomx-panel-render.so.0, omx-panel's renderer/include/omx_panel_render.h): its bars, its curves and its meters,
# in the omx look. This module is the ctypes door to it, and the host's side the renderer leaves to the host: which
# part of the panel a screen shows, the curve_bind line plugin-hostd draws a display's points from, and the reply
# of curve_points. Nothing here draws or computes a point: the renderer draws, plugin-hostd computes (omx-dsp's
# omx_curve_points), and a missing library is said by name.
#
# The renderer runs in a process of its own (zynthian-ui#44): a fault inside it stops that process, never the UI's. The
# UI's View sends each call to it over a socket and reads the drawn pixels from shared memory; when the renderer
# stops, the call raises RendererStopped, saying how, and the next View starts it again, up to STOPS_IN_A_ROW starts
# without a draw. The socket carries one call at a time, whatever thread makes it (zynthian-ui#79); a view's calls
# belong to Tk's thread (in_owner_thread), where the widgets make them. That shared memory is the one buffer every draw
# of a view goes into (zynthian-ui#59): with omx-panel#78's omx_panel_view_draw_dirty the renderer repaints only the
# cells that changed in it and says where, and PanelImage blits only those. This file is that process too (run as
# `python3 zynthian_omx_panel_view.py --serve <fd>`): it imports nothing but the standard library, and its sibling
# zynthian_contract_dir.py by its file, which imports nothing else either.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import ctypes
import importlib.util
import json
import logging
import math
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from multiprocessing import connection, shared_memory

# where omx-contract's contract directory is (zynthian_contract_dir), loaded from beside this file: this file also runs
# as a process of its own and as a file a test loads, where there is no zyngine package to import it from
_spec = importlib.util.spec_from_file_location("zynthian_contract_dir",
                                               os.path.join(os.path.dirname(os.path.abspath(__file__)), "zynthian_contract_dir.py"))
zynthian_contract_dir = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(zynthian_contract_dir)

LIBRARY = "libomx-panel-render.so.0"
# the look, the geometry and the font a view is made from: omx-panel's tools directory as the package installs it
TOOLS_DIR = "/usr/share/omx-panel/tools"

PIXEL_RGBA8_STRAIGHT = 2
# the most rectangles one dirty draw reports; the renderer merges what is over it, never drops one (omx_panel_view_draw_dirty)
RECTS = 32

# omx_panel_event_kind_t, omx_panel_key_t, omx_panel_pointer_t; the gesture words (omx_panel_word_t) are not listed
# here: word_name() asks the library for the name of the one an answer carries
EVENT_DOWN, EVENT_MOVE, EVENT_UP, EVENT_WHEEL, EVENT_DETENT, EVENT_KEY = range(6)
KEY_BACKSPACE, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT = range(5)
POINTER_TOUCH, POINTER_MOUSE = 0, 1


class RendererAbsent(Exception):
    """The renderer cannot be loaded or refuses the panel: the reason, said once by the caller."""


class RendererStopped(RendererAbsent):
    """The renderer's process stopped (a fault inside the library, or no answer): how, said once by the caller. The
    views it held are gone; the next View starts the renderer again, unless it stopped STOPS_IN_A_ROW times without a
    draw."""


class _Buffer(ctypes.Structure):
    _fields_ = [("pixels", ctypes.c_void_p), ("width", ctypes.c_uint32), ("height", ctypes.c_uint32),
                ("stride", ctypes.c_uint32), ("scale", ctypes.c_double), ("format", ctypes.c_int)]


class _Rect(ctypes.Structure):
    """omx_panel_rect_t: a rectangle of a buffer, in device px."""
    _fields_ = [("x", ctypes.c_uint32), ("y", ctypes.c_uint32), ("width", ctypes.c_uint32), ("height", ctypes.c_uint32)]


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
                _lib_error = f"omx-panel's renderer ({name}) is not installed: {e}"
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
    # a time_response's taps (omx_panel_view_set_stems, omx-panel 0.13.8): a renderer without it draws no tap, nothing else
    stems = getattr(lib, "omx_panel_view_set_stems", None)
    if stems is not None:
        stems.restype = B
        stems.argtypes = [P, U, DP, DP, DP, S, U]
    # the dirty draw (omx-panel#78): a renderer released before it has no such symbol, and the full draw is then the only
    # draw; no other shape of it is taken
    dirty = getattr(lib, "omx_panel_view_draw_dirty", None)
    if dirty is not None:
        dirty.restype = B
        dirty.argtypes = [P, ctypes.POINTER(_Buffer), ctypes.POINTER(_Rect), ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def _word_name(word):
    name = library().omx_panel_word_name(word)
    return None if name is None else name.decode()


def word_name(word):
    """The name of a gesture word as omx-panel's gestures.json spells it; "" for no word, None for a value that is none."""
    return _host().call("word", None, word)


def tools_dir():
    """The renderer's data directory: $ZYNTHIAN_OMX_PANEL_TOOLS, else where the omx-panel package installs it."""
    return os.environ.get("ZYNTHIAN_OMX_PANEL_TOOLS", TOOLS_DIR)


def look_dir(look, tools):
    """A data directory for the renderer carrying the host's <look> (a look document, zynthian_ui_look.tokens) as its
    look.json, and the renderer's own geometry, fonts and gesture declaration linked from <tools>: the renderer reads a
    look from a directory and copies what it reads, so the caller removes the directory once the view is made."""
    d = tempfile.mkdtemp(suffix=".look")
    with open(os.path.join(d, "look.json"), "w") as f:
        json.dump(look, f)
    for name in ("look", "fonts"):
        os.symlink(os.path.join(tools, name), os.path.join(d, name))
    # omx-panel's schema/gestures.json: beside the tools directory in the source tree, inside it where the package installs it
    for gestures in (os.path.join(tools, "gestures.json"), os.path.join(tools, "..", "schema", "gestures.json")):
        if os.path.exists(gestures):
            os.symlink(gestures, os.path.join(d, "gestures.json"))
            break
    return d


class _LibraryView:
    """One panel layout (what `omx-panel describe --layout` prints, or a part of it) as the renderer holds it, in the
    process that loaded the library: the renderer's process."""

    def __init__(self, layout, tools_dir_=None, look=None):
        lib = self.lib = library()
        self.layout = layout
        with tempfile.NamedTemporaryFile("w", suffix=".layout.json", delete=False) as f:
            json.dump(layout, f)
            path = f.name
        err = ctypes.create_string_buffer(512)
        tools = tools_dir_ or tools_dir()
        data = look_dir(look, tools) if look else None
        try:
            self.view = lib.omx_panel_view_create_from_files(path.encode(), (data or tools).encode(), err, len(err))
        finally:
            os.unlink(path)
            if data:
                shutil.rmtree(data, ignore_errors=True)
        if not self.view:
            raise RendererAbsent(f"omx-panel's renderer refused the panel: {err.value.decode(errors='replace')}")
        self.symbols = [lib.omx_panel_view_symbol(self.view, i).decode() for i in range(lib.omx_panel_view_count(self.view))]
        self.meters = [m["symbol"] for m in layout.get("meters") or []]
        self.size = None
        self.buffer = None  # the buffer the last draw went into, kept: the renderer repaints only what changed in it

    def close(self):
        if getattr(self, "view", None):  # none yet when the library refused the panel, or it could not be written
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

    def set_stems(self, display, stems):
        """The taps of a time_response display, curve_stems()'s (time ms, level dB, shade, letter); none clears them.
        False for a renderer with no stems, or stems it refuses."""
        set_stems = getattr(self.lib, "omx_panel_view_set_stems", None)
        if set_stems is None:
            return False
        n = len(stems)
        ts, dbs, shades = ((ctypes.c_double * n)(*(s[k] for s in stems)) for k in range(3))
        return set_stems(self.view, display, ts, dbs, shades, "".join(s[3] for s in stems).encode(), n)

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
        """The panel drawn into width x height pixels (RGBA, straight alpha, rows of width * 4 bytes), and where that draw
        changed them: (pixels, rects). The rects are (x, y, w, h) in device px, the renderer's own (zynthian-ui#59,
        omx-panel#78): the first draw and a new size are the whole panel as one, an unchanged panel none; None when the
        renderer has no dirty draw and drew the whole panel. The buffer is this view's own, kept between draws."""
        size = width * height * 4
        if self.buffer is None or len(self.buffer) != size:
            self.buffer = ctypes.create_string_buffer(size)
        rects = self.draw_into(self.buffer, width, height, scale)
        return self.buffer.raw, rects

    def draw_into(self, pixels, width, height, scale=1.0):
        """Draw into `pixels` (a writable buffer of width * height * 4 bytes: this view's own, or the UI's shared memory);
        the rects the draw changed, as draw() answers them. The renderer repaints only what changed when `pixels` is the
        buffer its last draw went into, still holding that draw: the caller keeps ONE buffer between draws, never a new
        one per draw, else every draw is the whole panel."""
        size = width * height * 4
        pixels = (ctypes.c_char * size).from_buffer(pixels)
        buf = _Buffer(ctypes.addressof(pixels), width, height, width * 4, scale, PIXEL_RGBA8_STRAIGHT)
        dirty = getattr(self.lib, "omx_panel_view_draw_dirty", None)
        if dirty is None:
            ok, rects = self.lib.omx_panel_view_draw(self.view, ctypes.byref(buf)), None
        else:
            found, count = (_Rect * RECTS)(), ctypes.c_size_t()
            ok = dirty(self.view, ctypes.byref(buf), found, RECTS, ctypes.byref(count))
            rects = [(r.x, r.y, r.width, r.height) for r in found[:count.value]]
        if not ok:
            raise RendererAbsent(f"omx-panel's renderer did not draw a {width} x {height} panel")
        return rects


# ---- The renderer's process ----

# a call answers within this, else the renderer is taken as stopped (a draw of the whole screen takes milliseconds)
ANSWER_S = 5.0
# a renderer started this many times without one draw between is not started again: each start costs a process and a
# library load, and one that stops on whatever it is given would be started at every page
STOPS_IN_A_ROW = 3

_the_host = None
_starting = threading.Lock()  # one thread starts the renderer
_starts = 0  # the renderer's starts since a view last drew
_given_up = False  # said once


def in_owner_thread():
    """Whether the caller is the thread a view's calls belong to: Tk's, the main thread. A view is opened, given its
    readings, drawn and closed as one sequence per widget; a page change that reaches a widget from another thread
    (the CUIA thread) gives that sequence to Tk's thread (after_idle), so no view is closed under a draw."""
    return threading.current_thread() is threading.main_thread()


def _attach(name):
    """The UI's shared memory, attached without the resource tracker taking it over (the UI owns it)."""
    return shared_memory.SharedMemory(name=name, track=False)


def _serve(fd):
    """The renderer's process: the views it holds by number, each call answered ("ok", value) or ("refused", why). A
    view's shared memory is attached at its first draw and let go when the view closes or draws into another (a
    bigger one): kept, each view ever drawn would hold a file of the process's 1024 (zynthian-ui#79)."""
    conn = connection.Connection(fd)
    views, memory, next_id = {}, {}, 1  # memory: view number => (name, the attached memory)

    def let_go(vid):
        held = memory.pop(vid, None)
        if held:
            held[1].close()

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
                let_go(vid)
                value = None
            elif op == "word":
                value = _word_name(*args)
            elif op == "draw":
                # drawn straight into the UI's shared memory: the one buffer kept between draws, so the renderer repaints
                # only what changed in it (the UI reads it, never writes it)
                name, width, height, scale = args
                name, width, height, scale = args
                if vid not in memory or memory[vid][0] != name:
                    let_go(vid)
                    memory[vid] = (name, _attach(name))
                rects = views[vid].draw_into(memory[vid][1].buf, width, height, scale)
                value = (width * height * 4, rects)
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
        # a call and its answer, whole: the plot task (Tk's thread), a page change (the CUIA thread) and a view freed
        # by the collector (any thread) share this connection, and two calls at once read each other's answers
        self.turn = threading.Lock()

    def call(self, op, vid, *args):
        with self.turn:
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
    """The renderer's process, started again when the last one stopped; RendererStopped, said once, when it was started
    STOPS_IN_A_ROW times and no view drew."""
    global _the_host, _starts, _given_up
    with _starting:
        if _the_host is None or not _the_host.alive():
            if _starts >= STOPS_IN_A_ROW:
                why = (f"omx-panel's renderer stopped {STOPS_IN_A_ROW} times in a row without a draw: it is not started "
                       "again in this session")
                if not _given_up:
                    _given_up = True
                    logging.error(why)
                raise RendererStopped(why)
            _starts += 1
            _the_host = _Host()
        return _the_host


def _drew():
    """A view drew: the renderer works, and the count of its starts begins again."""
    global _starts
    _starts = 0


class View:
    """One panel layout (what `omx-panel describe --layout` prints, or a part of it) as the renderer holds it, in the
    renderer's process: each call is the library's, its answer the library's. RendererStopped when that process
    stopped."""

    def __init__(self, layout, tools_dir=None, look=None):
        """<look>: the host's look document (zynthian_ui_look.tokens) the panel is drawn in; None draws it in the
        renderer's own look."""
        self.host = _host()
        self.layout = layout
        self.id, self.symbols = self.host.call("open", None, layout, tools_dir, look)
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

    def set_stems(self, display, stems):
        return self._call("set_stems", display, [tuple(s) for s in stems])

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
        """The panel drawn into width x height pixels (RGBA, straight alpha, rows of width * 4 bytes), and where that draw
        changed them: (pixels, rects), as _LibraryView.draw answers them. The renderer's process draws into this view's
        shared memory, the one buffer kept between draws; it is made anew only when a draw needs more of it."""
        size = width * height * 4
        if self.memory is None or self.memory.size < size:
            if self.memory:
                self.memory.close()
                self.memory.unlink()
            self.memory = shared_memory.SharedMemory(create=True, size=size)
        n, rects = self._call("draw", self.memory.name, width, height, scale)
        _drew()
        return bytes(self.memory.buf[:n]), rects


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

_curve_words = {}  # curve.json => (display kinds, role words)


def curve_words(root=None):
    """(the display kinds drawn from a curve, the role words a curve is bound by) as omx-dsp declares them:
    CURVE_DISPLAYS and CURVE_ROLES of the curve.json its contract package installs, in the wire's spelling (snake
    case, the description's own words). A role of the description that is none of these (attack, release) is not
    bound; one the family's curve does not read (a compressor's mix) is bound and draws nothing. Two empty tuples when the declaration cannot be read: no display is a curve then.
    The file is <contractdir>/omx-dsp/primitives/curve.json, in the contract directory given or else the installed
    one (zynthian_contract_dir)."""
    path = zynthian_contract_dir.find("omx-dsp", "primitives", "curve.json", dirs=None if root is None else [root])
    if path is None:
        logging.warning("omx-dsp's curve.json is in no contract directory: no curve is drawn")
        return (), ()
    if path not in _curve_words:
        def wire(ids):
            return tuple("".join("_" + c.lower() if c.isupper() else c for c in i) for i in ids)
        try:
            with open(path) as f:
                doc = json.load(f)
            _curve_words[path] = wire(doc["CURVE_DISPLAYS"]["ids"]), wire(doc["CURVE_ROLES"]["ids"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            logging.warning("omx-dsp's curve.json is not readable (%s): no curve is drawn", e)
            return (), ()
    return _curve_words[path]


_curve_legs = {}  # curve.json => leg words


def curve_legs(root=None):
    """The leg words a delay's tap lands on, omx-dsp's CURVE_LEGS of the curve.json curve_words reads, in their order
    (the first is the dry tap's, on both legs); () when the declaration cannot be read, said once per file."""
    path = zynthian_contract_dir.find("omx-dsp", "primitives", "curve.json", dirs=None if root is None else [root])
    if path is None:
        return ()
    if path not in _curve_legs:
        try:
            with open(path) as f:
                _curve_legs[path] = tuple(json.load(f)["CURVE_LEGS"]["ids"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            logging.warning("omx-dsp's curve.json declares no readable CURVE_LEGS (%s): no tap is drawn", e)
            _curve_legs[path] = ()
    return _curve_legs[path]


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
    """The points of a curve_points reply, ascending in x; [] for a reply that is not one. The reply is
    '<count> <marks> <x>,<y> ...' (plugin-hostd-protocol's curve-points-reply): the marks are one word after the count,
    '-' when none, each band a feedback corrector planted otherwise; a delay's taps follow the points ('stems ...').
    Neither is a point: the marks and the taps are not drawn here."""
    words = reply.split()
    try:
        n = int(words[0])
        if len(words) < 2 or words[1].count(",") == 1:
            return []  # no marks word: a reply of another grammar
        points = [tuple(float(v) for v in w.split(",")) for w in words[2:n + 2]]
    except (IndexError, ValueError):
        return []
    if len(points) != n or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        return []
    return points


def curve_stems(reply):
    """The taps of a curve_points reply, each (time ms, level dB, shade 0..1, letter) as omx-panel's renderer takes a
    stem (omx_panel_view_set_stems); None for a reply with no taps or a malformed one. A delay's time_response answers
    them after the points, 'stems <count> <t>,<dB>,<shade>,<leg> ...' (plugin-hostd-protocol's curve-points-reply).
    The letter is the leg's, as CURVE_LEGS says it (curve_legs): none for the first, the dry tap's on both legs, else
    the leg word's initial; a leg word it does not hold refuses the reply."""
    words = reply.split()
    if "stems" not in words:
        return None
    at = words.index("stems")
    legs = curve_legs()
    try:
        int(words[0])
        n = int(words[at + 1])
        stems = []
        for w in words[at + 2:]:
            t, db, shade, leg = w.split(",")
            stems.append((float(t), float(db), float(shade), " " if leg == legs[0] else leg[0].upper()))
            if leg not in legs or not all(math.isfinite(v) for v in stems[-1][:3]):
                return None
    except (IndexError, ValueError):
        return None
    return stems if len(stems) == n else None


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
