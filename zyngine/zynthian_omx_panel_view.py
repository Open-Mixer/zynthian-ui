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
import re
import signal
import subprocess
import tempfile
import threading

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
    # the spectrum layer (omx-panel 0.14): a renderer without it draws every panel, with no spectrum under a curve
    f = getattr(lib, "omx_panel_view_set_spectrum", None)
    if f is not None:
        f.restype, f.argtypes = B, [P, U, DP, DP, DP, U, D, D, D]


def word_name(word):
    """The name of a gesture word as omx-panel's gestures.json spells it; "" for no word, None for a value that is none."""
    name = library().omx_panel_word_name(word)
    return None if name is None else name.decode()


class View:
    """One panel layout (what `omx-panel describe --layout` prints, or a part of it) as the renderer holds it."""

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

    def set_spectrum(self, display, frame, mode, delta, window):
        """The spectrum under display `display`'s curve: a frame of rta_frame() (None clears it), drawn in the console's
        `mode` (pre, post or both) with or without the `delta`, on the level window (db_min, db_max, grid_db). False
        for a display the renderer refuses (no log axis) and for a renderer without the layer."""
        f = getattr(self.lib, "omx_panel_view_set_spectrum", None)
        if f is None or not window:
            return False
        tap = None if frame is None else (frame["pre"] if mode == "pre" else frame["post"] or frame["pre"])
        if tap is None:
            return bool(f(self.view, display, None, None, None, 0, *window))
        # the renderer's single-trace entry (omx-panel 0.14.0): the tap the mode shows; both and the delta wait for the
        # amended entry that takes pre, post and the mode
        n = len(frame["hz"])
        arr = ctypes.c_double * n
        return bool(f(self.view, display, arr(*frame["hz"]), arr(*tap[0]), arr(*tap[1]), n, *window))

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
        return [(c.control, c.fraction, c.value) for c in changes[:k]], word_name(a.word), a.selected

    def tick(self, t_ms):
        changes = (_Change * 64)()
        a = _Answer()
        k = self.lib.omx_panel_view_tick(self.view, t_ms, changes, 64, ctypes.byref(a))
        return [(c.control, c.fraction, c.value) for c in changes[:k]], word_name(a.word), a.selected

    def draw(self, width, height, scale=1.0):
        """The panel drawn into width x height pixels: RGBA, straight alpha, rows of width * 4 bytes."""
        pixels = ctypes.create_string_buffer(width * height * 4)
        buf = _Buffer(ctypes.cast(pixels, ctypes.c_void_p), width, height, width * 4, scale, PIXEL_RGBA8_STRAIGHT)
        if not self.lib.omx_panel_view_draw(self.view, ctypes.byref(buf)):
            raise RendererAbsent(f"omx-panel's renderer did not draw a {width} x {height} panel")
        return pixels.raw


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


# ---- The spectrum under a curve: omx-rta-read as the panel's child (openmixer's spec 2026-11-15, zynthian RTA §3, §6) ----

READER = "omx-rta-read"
MODES = ("pre", "post", "both")


def rta_argv(mode, post_ports, pre_ports, bands, exe=None):
    """The reader's command line for the console's `mode`: --post for post, --pre for pre, both for both, each port
    named; None when the mode is none of these or a tap it shows is not answered (a tap nobody shows is never read)."""
    if mode not in MODES or (mode != "pre" and not post_ports) or (mode != "post" and not pre_ports):
        return None
    argv = [exe or os.environ.get("ZYNTHIAN_OMX_RTA_READ", READER)]
    for tap, ports in (("--post", post_ports if mode != "pre" else []), ("--pre", pre_ports if mode != "post" else [])):
        for port in ports:
            argv += [tap, port]
    return argv + ["--bands", str(int(bands))]


def rta_taps(client, sharing, instance, get_ports):
    """(post ports, pre ports, refusal) of `instance` (spec §3.3): the audio outputs of its jack client for POST, the
    audio inputs for PRE. `sharing` is the instances the client runs, in chain order ([instance] for a client of its
    own): only the LAST answers POST and only the FIRST answers PRE, so a member inside a grouped chain answers neither
    and is refused by name, never given another signal's spectrum. `get_ports` is jack's (pattern, is_input)."""
    if not client:
        return [], [], "no jack client"
    first, last = (not sharing or sharing[0] == instance), (not sharing or sharing[-1] == instance)

    def audio(is_input):
        return [p.name for p in get_ports(f"^{re.escape(client)}:", is_input=is_input) if getattr(p, "is_audio", True)]
    post, pre = audio(False) if last else [], audio(True) if first else []
    return post, pre, None if (first or last) else "no spectrum inside a grouped chain"


RTA_PATH = os.path.join("3", "omx-dsp", "primitives", "rta.json")
_rta_window_said = set()  # the contract roots whose rta.json was said unreadable


def rta_window(root=None):
    """(db_min, db_max, grid_db): the level window omx-dsp declares (RTA_LEVEL_DB_MIN, RTA_LEVEL_DB_MAX,
    RTA_LEVEL_GRID_DB of the rta.json its contract package installs), never restated here; None, said once, when it
    cannot be read, and no spectrum is drawn then."""
    root = root or (os.environ.get("OMX_CONTRACT_PATH") or CONTRACT_PATH).split(":")[0]
    try:
        with open(os.path.join(root, RTA_PATH)) as f:
            doc = json.load(f)

        def number(key):
            v = doc[key]
            v = v.get("value") if isinstance(v, dict) else v
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f"{key} is no number")
            return float(v)
        window = number("RTA_LEVEL_DB_MIN"), number("RTA_LEVEL_DB_MAX"), number("RTA_LEVEL_GRID_DB")
        if not (window[0] < window[1] and window[2] > 0):
            raise ValueError(f"{window} is no level window")
        return window
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        if root not in _rta_window_said:
            _rta_window_said.add(root)
            logging.warning("omx-dsp's rta.json is not readable (%s): no spectrum is drawn", e)
        return None


def rta_bands(width_px):
    """As many bands as the display's width supports: one per 6 px, 16 to 64."""
    return max(16, min(64, int(width_px) // 6))


def _levels(values, n):
    if not isinstance(values, list) or len(values) != n:
        raise ValueError("a level list of another length")
    out = []
    for v in values:
        if v is None:
            out.append(float("-inf"))
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            out.append(float(v))
        else:
            raise ValueError("a level that is no number")
    return out


def rta_frame(line):
    """One of the reader's lines as {"hz", "post": (db, peak) | None, "pre": (db, peak) | None, "diff": [...] | None},
    a null level as -INFINITY (silence); None for a line that is no frame."""
    try:
        doc = json.loads(line)
        hz = doc["hz"]
        if not isinstance(hz, list) or len(hz) < 2:
            return None
        hz = [float(h) for h in hz]
        if not all(math.isfinite(h) and h > 0 for h in hz) or any(b <= a for a, b in zip(hz, hz[1:])):
            return None
        frame = {"hz": hz, "post": None, "pre": None, "diff": None}
        for tap in ("post", "pre"):
            if doc.get(tap) is not None:
                frame[tap] = (_levels(doc[tap]["db"], len(hz)), _levels(doc[tap]["peak"], len(hz)))
        if frame["post"] is None and frame["pre"] is None:
            return None
        if doc.get("diff") is not None:
            frame["diff"] = _levels(doc["diff"], len(hz))
        return frame
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


class SpectrumFeed:
    """The reader of one shown panel: a child in its own process group, its stdout read by a thread that keeps the
    newest frame; apply() hands that frame to the view's displays on the caller's (the UI's) thread, at most once per
    frame; stop() ends the child (SIGTERM, then SIGKILL after `grace`) and reaps it. A reader that ends by itself clears
    the spectrum and is said once by its exit status; a missing reader is named once and nothing runs."""

    def __init__(self, view, displays, argv, mode, delta, window):
        self.view, self.displays, self.argv = view, list(displays), list(argv)
        self.mode, self.delta, self.window = mode, bool(delta), window
        self.proc = self.thread = None
        self.lock = threading.Lock()
        self.frame = None
        self.fresh = False      # a frame (or the end) the view has not been given
        self.ended = None       # the reader's exit status once it ended by itself
        self.refused = set()    # displays the view refused: said once, not fed again
        self.stopping = False

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        try:
            self.proc = subprocess.Popen(self.argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        except OSError as e:
            logging.warning("%s cannot be started (%s): the panel shows no spectrum", READER, e)
            self.proc = None
            return False
        self.thread = threading.Thread(target=self._read, name="omx-rta-read", daemon=True)
        self.thread.start()
        return True

    def _read(self):
        proc = self.proc
        for line in proc.stdout:
            frame = rta_frame(line)
            if frame is not None:
                with self.lock:
                    self.frame, self.fresh = frame, True
        status = proc.wait()
        if not self.stopping:
            logging.warning("%s ended by itself with status %s: the panel shows no spectrum", READER, status)
            with self.lock:
                self.frame, self.fresh, self.ended = None, True, status

    def apply(self):
        """Hand the newest frame (or the end's empty spectrum) to the view; True when the view was given anything."""
        with self.lock:
            if not self.fresh:
                return False
            frame, self.fresh = self.frame, False
        given = False
        for d in self.displays:
            if d in self.refused:
                continue
            if self.view.set_spectrum(d, frame, self.mode, self.delta, self.window):
                given = True
            elif frame is not None:
                self.refused.add(d)
                logging.warning("the renderer refuses a spectrum on display %s: it is not fed again", d)
        return given

    def stop(self, grace=1.0):
        proc, self.stopping = self.proc, True
        if proc is None:
            return
        if proc.poll() is None:
            for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    proc.wait(wait)
                    break
                except subprocess.TimeoutExpired:
                    continue
        proc.wait()
        if self.thread is not None:
            self.thread.join(2.0)
        proc.stdout.close()
        self.proc = self.thread = None
