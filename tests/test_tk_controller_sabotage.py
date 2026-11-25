# -*- coding: utf-8 -*-
#
# Sabotage arms of the Tk controller (zynthian-ui#93 stage 1): each arm breaks one thing in a COPY of the tree and runs
# test_tk_controller.py there; every arm must turn it red, and the unbroken copy must stay green (the control, which
# proves the copy runs the same tests).
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TK = os.path.join("zyngui", "zynthian_gui_controller_tk.py")
CONFIG = os.path.join("zyngui", "zynthian_gui_config.py")
GESTURES = os.path.join("zyngine", "zynthian_panel_gestures.py")

ARMS = {
    "a rule of its own for the kind": ('zynthian_panel_gestures.widget_of(zctrl)', '("switch" if zctrl.is_toggle else "selector" if zctrl.ticks else "fader")'),
    "the gesture rule forgets the engine's word": ('is_toggle and getattr(zctrl, "toggle_declared", None) is not False', 'is_toggle', GESTURES),
    "an image per value": ('            x0, y0, radius = self.centre\n', '            x0, y0, radius = self.centre\n            self.photo_of(knob_face(2 * radius, tokens()))\n'),
    "no cache": ('    if key in FACES:\n        return FACES[key]\n    from PIL import Image, ImageColor, ImageDraw\n    t = {k: ImageColor.getrgb(v)[:3] for k, v in tokens}\n    S',
                 '    from PIL import Image, ImageColor, ImageDraw\n    t = {k: ImageColor.getrgb(v)[:3] for k, v in tokens}\n    S'),
    "a travel of 180 degrees": ("KNOB_DEG = 270", "KNOB_DEG = 180"),
    "a default filled in for a token": ("os.environ.get('ZYNTHIAN_UI_COLOR_KNOB_EDGE') or None", "os.environ.get('ZYNTHIAN_UI_COLOR_KNOB_EDGE') or '#000000'", CONFIG),
    "no refusal of a short preset": ('if ui_look == "vintage" and not all(', 'if False and not all(', CONFIG),
    "an after_idle hop": ('        def draw(self):\n            if self.hidden:', '        def draw(self):\n            if self.hidden or self.after_idle(lambda: None):'),
    "the cap gradient the wrong way": ('_mix(t["color_knob_face"], t["color_knob_cap_hi"], u)', '_mix(t["color_knob_cap_hi"], t["color_knob_face"], u)'),
    "a tick in the wrong colour": ('TICK_IN, TICK_OUT, t["color_hl"]', 'TICK_IN, TICK_OUT, t["color_knob_edge"]'),
    "a bipolar control's zero not put back": ('plot -= z.value_min / z.value_range', 'pass'),
    "the renderer is asked for": ('import tkinter\n', 'import tkinter\nfrom zyngine import zynthian_omx_panel_view  # noqa\n'),
    "a canvas call from the value's thread": ('        def plot_value(self):\n            refresh', '        def calculate_plot_values(self):\n            super().calculate_plot_values()\n            self.draw()\n\n        def plot_value(self):\n            refresh'),
    "the stock arc shown": ('            self.itemconfig(self.graph, state=tkinter.HIDDEN)\n            getattr', '            getattr'),
    "the items above the text": ('                self.tag_lower(item)', '                self.tag_raise(item)'),
}


def run_copy(mutation=None):
    with tempfile.TemporaryDirectory() as tmp:
        # upstream's tests/conftest.py imports zyngine's state manager, which reads zynconf, zynautoconnect and zynlibs
        for d in ("zyngine", "zyngui", "zynconf", "zynautoconnect", "zynlibs", "tests", ".github"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__"))
        if mutation:
            old, new, *module = mutation
            path = os.path.join(tmp, module[0] if module else TK)
            with open(path) as f:
                code = f.read()
            assert code.count(old) >= 1, f"the arm did not land: {old!r} is not in the module"
            with open(path, "w") as f:
                f.write(code.replace(old, new))
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                               os.path.join(tmp, "tests", "test_tk_controller.py")],
                              cwd=tmp, capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", ZYNTHIAN_TK_SABOTAGE_COPY="1"))


@unittest.skipIf(os.environ.get("ZYNTHIAN_TK_SABOTAGE_COPY"), "inside a copy: the arms do not nest")
class SabotageArms(unittest.TestCase):

    def test_the_unbroken_copy_is_green(self):
        r = run_copy()
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])

    def test_every_arm_turns_the_tk_controller_red(self):
        for name, mutation in ARMS.items():
            with self.subTest(arm=name):
                r = run_copy(mutation)
                self.assertNotEqual(r.returncode, 0, f"the arm {name!r} left every test green")
