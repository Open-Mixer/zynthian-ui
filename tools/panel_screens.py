# -*- coding: utf-8 -*-
#
# The control screens of REAL plugins as the UI draws them, by hand (not collected by CI): the screenshots of
# docs/openmixer-panels-on-zynthian.md. The engine of this tree adds each plugin to a plugin-hostd already listening on
# PHD_PORT (its feedback port PHD_PORT + 1, a jackd of its own), exactly as tools/pi/drawn_panel_on_the_pi.py does;
# then the UI's own control screen (zyngui/zynthian_gui_control.py, its four controllers and, for a panel with bars,
# a curve or a meter, the panel's screen zynthian_widget_omx_panel) is built on a Tk display of the Zynthian's size and
# walked through every page the screen lists. Each page is taken from the X display with ImageMagick's `import`.
#
# Only the UI object (zynthian_gui) is a stand-in: it answers the current processor and the chain's processors. The
# native layer is the suite's fakes (tests/bootstrap.py). The process draws one display size and one look, so run it
# once per pair:
#
#   Xvfb :9 -screen 0 1024x768x24 &  DISPLAY=:9 W=480 H=320 WIRING=V4 LOOK=stock OUT=/tmp/shots \
#   PHD_PORT=17556 PHD_URIS="clap:/usr/lib/clap/omx-strip.clap#org.openmixer.strip" \
#   ZYNTHIAN_OMX_PANEL_RENDER=/usr/lib/x86_64-linux-gnu/libomx-panel-render.so.1 \
#   python3 -m pytest -s tools/panel_screens.py
#
# LOOK=vintage sources zynthian-sys's config/ui-looks/openmixer-vintage.sh (VINTAGE names the file). The daemon must run
# the plugin (on a desk with no qualification records: `require_pins 0` in its -c file), or the page cut misses the
# plugin's own remote-controls pages and every value is its default. Pass `-o timeout=0`: a plugin's pages take more
# than the suite's per-test minute.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import json
import os
import re
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tests"), ROOT]
import tests.bootstrap  # noqa: E402,F401  the fake native layer, before any production module

W, H = int(os.environ.get("W", "480")), int(os.environ.get("H", "320"))
LOOK = os.environ.get("LOOK", "stock")
OUT = os.environ.get("OUT", "/tmp/shots")
PORT = int(os.environ.get("PHD_PORT", "17556"))
URIS = os.environ.get("PHD_URIS", "clap:/usr/lib/clap/omx-strip.clap#org.openmixer.strip").split()
SETTLE = float(os.environ.get("SETTLE", "1.5"))

# the UI's settings, after tests.bootstrap dropped every inherited ZYNTHIAN_* variable
os.environ.update(DISPLAY_WIDTH=str(W), DISPLAY_HEIGHT=str(H), ZYNTHIAN_WIRING_LAYOUT=os.environ.get("WIRING", "V4"),
                  ZYNTHIAN_UI_LOOK=LOOK)
if LOOK == "vintage":
    with open(os.environ["VINTAGE"]) as f:
        for line in f:
            m = re.match(r'export (ZYNTHIAN_UI_[A-Z0-9_]+)="?([^"\n]*)"?', line)
            if m:
                os.environ[m.group(1)] = m.group(2)
sys.argv[0] = "zynthian_main.py"  # zynthian_gui_config opens its Tk display only for the UI's own main

from zyngine import zynthian_state_manager  # noqa: E402,F401  the real package first, in the order the UI imports in
from zyngui import zynthian_gui_config as cfg  # noqa: E402
from test_engine_plugin_hostd import plugin_hostd_case, ph  # noqa: E402
from zyngine import zynthian_plugin_hostd_catalogue as cat  # noqa: E402


def slug(text):
    return re.sub(r"-+", "-", "".join(c if c.isalnum() else "-" for c in text)).strip("-").lower()[:48]


class Screens(plugin_hostd_case):

    def setUp(self):
        super().setUp()
        os.environ["PATH"] = "/usr/bin:/bin"  # the installed omx-panel and node
        self.port = PORT
        ph.daemon = ph.plugin_hostd_daemon(PORT)
        ph.daemon.start_script = os.path.join(self.tmp, "not-installed")
        os.makedirs(OUT, exist_ok=True)

    def add_real(self, uri, n):
        """The plugin as the UI's catalogue has it from omx-clap-scan of its directory (its name, its features)."""
        path = uri[5:].partition("#")[0]
        scan = json.loads(subprocess.run(["omx-clap-scan", "--json", os.path.dirname(path)], capture_output=True,
                                         text=True, check=True, timeout=300).stdout)
        cat.add_catalogue(self.info, clap=cat.scanned_plugins(scan), binary="/usr/bin/plugin-hostd")
        return self.add(self.chain(n), "PH/" + uri)

    def control_screen(self, proc):
        from unittest import mock
        from zyngui.zynthian_gui_control import zynthian_gui_control
        zyngui = mock.MagicMock()
        zyngui.get_current_processor.return_value = proc
        zyngui.get_alt_mode.return_value = False
        zyngui.zynpot_pr_state = [0] * 4
        zyngui.chain_manager.get_processors.return_value = [proc]
        sm = zyngui.state_manager  # the topbar's status: nothing muted, recording or playing
        sm.zynmixer_bus.get_mute.return_value = False
        sm.audio_recorder.status = sm.status_audio_player = sm.status_midi_recorder = sm.status_midi_player = False
        sm.zynseq.libseq.isMidiRecord.return_value = False
        sm.zynseq.playing_sequences = 0
        sm.status_xrun = sm.status_undervoltage = sm.status_overtemp = False
        sm.status_cpu_load = 10
        zyngui.after_idle = cfg.top.after_idle  # the screen shows its widget on Tk's idle time
        zyngui.after = cfg.top.after
        cfg.zyngui = zyngui
        screen = zynthian_gui_control()
        screen.chain_manager, screen.state_manager = zyngui.chain_manager, sm
        return screen

    def take(self, name):
        top = cfg.top
        end = time.monotonic() + SETTLE
        while time.monotonic() < end:  # the widget builds on Tk's idle time and the renderer draws from it
            top.update()
            time.sleep(0.02)
        path = os.path.join(OUT, name + ".png")
        subprocess.run(["import", "-window", "root", "-crop", f"{W}x{H}+0+0", "+repage", path], check=True)
        return path

    def test_every_page_of_each_plugin(self):
        for n, uri in enumerate(URIS, 1):
            proc = self.add_real(uri, n)
            engine = proc.engine
            deadline = time.monotonic() + 30
            while not engine.drawn and time.monotonic() < deadline and not engine._ctrl_screens:
                time.sleep(1)
                engine.set_drawn_view()
            stem = slug(uri.rpartition("/")[2].split(".")[0])
            layout = engine.drawn[0] if engine.drawn else {}
            print(f"\n{uri}: {len(engine._ctrl_screens)} pages, panel screen "
                  f"{os.path.basename(engine.custom_gui_fpath or '-')}, displays "
                  f"{[d.get('kind') for d in layout.get('displays') or []]}, meters {len(layout.get('meters') or [])}",
                  flush=True)
            screen = self.control_screen(proc)
            screen.build_view()
            screen.fill_list()
            screen.show()
            pages = [i for i, row in enumerate(screen.list_data) if len(row) >= 5 and row[1] != -1]
            print(f"  screens {[name for name, _ in engine._ctrl_screens]}", flush=True)
            for k, i in enumerate(pages):
                screen.set_mode_control()
                screen.select(i)
                for _ in range(3):
                    cfg.top.update()
                    screen.plot_zctrls(force=True)
                title = screen.list_data[i][2]
                zs = [z.short_name if z else "-" for z in (screen.zcontrollers or [])]
                path = self.take(f"{stem}-{W}x{H}-{LOOK}-{k:02d}-{slug(title)}")
                print(f"  page {k:02d} {title!r}: {zs} -> {os.path.basename(path)}", flush=True)
            # the list of pages (the screen in select mode): the home of the plugin's controls
            screen.set_mode_select()
            cfg.top.update()
            screen.hide_widgets()
            screen.select(pages[0])
            path = self.take(f"{stem}-{W}x{H}-{LOOK}-home")
            print(f"  home (page list) -> {os.path.basename(path)}", flush=True)
            screen.hide()
            screen.destroy()


if __name__ == "__main__":
    unittest.main()
