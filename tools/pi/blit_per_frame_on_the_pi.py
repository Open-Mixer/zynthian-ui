# -*- coding: utf-8 -*-
#
# The cost of one drag frame of a drawn panel on the Pi, by hand (not collected by CI; zynthian-ui#44): a bar of the
# graphic EQ and a band dot of eq8 dragged for DRAG_S seconds each, at the widget's size on the 1024 px screen. Each frame is
# what the panel widget does on a drag (zyngui/zynthian_widget_omx_panel.py, drawn_input then paint): the event to the
# renderer, its draw (into the one buffer the view keeps: with omx-panel#78's renderer only the changed cells, and it
# says which), the blit (the panel image module's PanelImage, the widget's own path: only those cells, else the rows
# the draw changed, converted over the background and copied into the photo on the screen, #59), and the canvas update,
# each timed.
# Frames run back to back: the frame rate is what the screen reached. Run once in the renderer's own process (the
# panel view's View, as the UI runs it now) and once with the library in this process (the view before #44), so the
# process boundary's cost is the difference. One JSON line per run goes to stdout; the figures go into
# docs/blit-per-frame-on-the-pi.md with the commit they were measured at. A p99 frame above one display frame
# (16.7 ms at 60 Hz) is red.
#
#   DISPLAY=:0 XAUTHORITY=... ZYNTHIAN_OMX_PANEL_TOOLS=/usr/share/omx-panel/tools DRAG_S=30 W=1024 H=416 \
#   python3 tools/pi/blit_per_frame_on_the_pi.py
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import json
import os
import subprocess
import sys
import time
import tkinter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
# the view module by its path, as the tests load it: the zyngine package needs the Zynthian's native libraries
_spec = importlib.util.spec_from_file_location("panel_view", os.path.join(ROOT, "zyngine", "zynthian_omx_panel_view.py"))
pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pv)
_spec = importlib.util.spec_from_file_location("panel_image", os.path.join(ROOT, "zyngui", "zynthian_gui_omx_panel_image.py"))
pi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pi)

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "omx_panel")
SECONDS = float(os.environ.get("DRAG_S", "30"))
W, H = int(os.environ.get("W", "1024")), int(os.environ.get("H", "416"))
FRAME_MS = 1000.0 / 60
DRAGS = (("bar", "omx-geq", "band08"), ("band dot", "omx-eq8", "b3_freq"))


def layout(name, symbol):
    with open(os.path.join(FIXTURES, f"{name}.json")) as f:
        part, _ = pv.screen_part(json.load(f)["layout"], {symbol})
    return part


def quantiles(ms):
    s = sorted(ms)
    at = lambda q: s[min(len(s) - 1, int(q * len(s)))]  # noqa: E731
    return {"p50": round(at(0.50), 2), "p99": round(at(0.99), 2), "max": round(s[-1], 2)}


def drag(view_class, what, name, symbol, root, canvas):
    view = view_class(layout(name, symbol))
    view.set_surface(W, H)
    i = view.symbols.index(symbol)
    for k in range(len(view.symbols)):
        view.set_value(k, 0.5, "")
    (x, y, w, h), travel = view.target_rect(i)
    cx, cy = x + w / 2, y + h / 2
    screen = pi.PanelImage("#000000", canvas)
    t0 = time.monotonic()
    view.input(pv.EVENT_DOWN, t0 * 1000.0, cx, cy)
    parts = {"input": [], "draw": [], "blit": [], "canvas": [], "frame": []}
    blitted = []  # the pixels blitted per frame: the area of the boxes PanelImage copied
    n = 0
    while time.monotonic() - t0 < SECONDS:
        n += 1
        a = time.monotonic()
        offset = travel * 0.4 * (1 if (n // 60) % 2 else -1) * ((n % 60) / 60.0)  # up and down the travel
        # a drag is vertical, up to raise, as the gestures declare it for a bar and a dot alike (a sideways drag moved
        # nothing: the frames of 16596f12's bar rows were all the same draw)
        changes, _, _ = view.input(pv.EVENT_MOVE, a * 1000.0, cx, cy - offset)
        for c, fraction, _ in changes:
            view.set_value(c, fraction, "")
        b = time.monotonic()
        rgba, dirty = view.draw(W, H)
        c = time.monotonic()
        blitted.append(sum(box[2] * box[3] for box in screen.show(rgba, W, H, dirty)))
        d = time.monotonic()
        root.update()
        e = time.monotonic()
        for k, v in (("input", b - a), ("draw", c - b), ("blit", d - c), ("canvas", e - d), ("frame", e - a)):
            parts[k].append(v * 1000.0)
    view.input(pv.EVENT_UP, time.monotonic() * 1000.0, cx, cy)
    view.close()
    elapsed = time.monotonic() - t0
    result = {"drag": what, "plugin": name, "control": symbol, "size": f"{W}x{H}", "frames": n,
              "fps": round(n / elapsed, 1)}
    result.update({k: quantiles(v) for k, v in parts.items()})
    result["pixels blitted"] = quantiles(blitted)
    result["red"] = result["frame"]["p99"] > FRAME_MS
    return result


def main():
    commit = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True).stdout.strip()
    root = tkinter.Tk()
    root.geometry(f"{W}x{H}+0+0")
    canvas = tkinter.Canvas(root, width=W, height=H, highlightthickness=0, bg="#000000")
    canvas.pack()
    root.update()
    red = False
    modes = [("renderer process", pv.View), ("in the UI's process", pv._LibraryView)]
    if os.environ.get("ORDER") == "in-process-first":  # the order is varied: a run must not owe its figure to its place
        modes.reverse()
    for where, view_class in modes:
        for what, name, symbol in DRAGS:
            r = drag(view_class, what, name, symbol, root, canvas)
            r.update(where=where, commit=commit)
            red |= r["red"]
            print(json.dumps(r), flush=True)
    root.destroy()
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
