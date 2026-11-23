# -*- coding: utf-8 -*-
#
# The Zynthian screens are omx-panel's pages and nothing else (panel spec 7.14). Three things guard it:
#  - the files omx-panel's cut was recorded in (tests/fixtures/plugin_hostd/<name>.pages<N>.json) are what the real
#    command prints: with OMX_PANEL_REAL ('node path/to/omx-panel.mjs') every one is run again and compared, so a
#    recording cannot drift from the cut it stands for (the tests of the engine replay them);
#  - no page size is written in the engine's page code: the width is SURFACE_WIDTH, declared once;
#  - sabotage arms, each in a COPY of zyngine/ and tests/: Easy dropped, the cut reordered after omx-panel (a skin
#    applied after it), a hidden slot reflowed, a surface page-size literal, the base cutter asked again, the old merge
#    that drops a control a second page shows. Every arm must turn the page tests red, and the unbroken copy stay green.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import inspect
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

from tests.tree_copy import copy_core

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures", "plugin_hostd")
ENGINE = os.path.join("zyngine", "zynthian_engine_plugin_hostd.py")
# omx-eq8 (omx-plugins 0.19.3's descriptor, through omx-panel's corpus) and calf-mbc (omx-panel's Calf-multiband-compressor-
# shaped test descriptor) are recorded from omx-panel v0.15.1 (3cace582), which carries the group model (omx-panel#63, #71),
# the commit the workflow builds, under the contract set the workflow installs from the channel (omx-contract-data 3.20.2,
# plugin-hostd-contract 0.20.8, omx-plugins-contract 0.19.3, whose role meanings make omx-eq8 an EQ; omx-dsp-contract 0.33.1,
# omx-clap-core-contract 0.33.1, plugin-db-contract 0.4.7, plugin-hostd-protocol-contract 0.7.0).
NAMES = ("big", "synth", "eq", "authored", "omx-eq8", "calf-mbc")


class RecordedCutIsTheRealCut(unittest.TestCase):

    @unittest.skipUnless(os.environ.get("OMX_PANEL_REAL"), "OMX_PANEL_REAL is 'node path/to/omx-panel.mjs', the real command")
    def test_every_recording_is_what_omx_panel_prints(self):
        real = shlex.split(os.environ["OMX_PANEL_REAL"])
        for name in NAMES:
            descriptor = os.path.join(FIXTURES, f"{name}.descriptor.json")
            for kind, args in (("describe", []), ("pages4", ["--pages", "--per-page", "4"]), ("pages8", ["--pages", "--per-page", "8"])):
                with self.subTest(f"{name} {kind}"):
                    out = subprocess.run(real + ["describe", "--descriptor", descriptor, *args], capture_output=True, text=True, check=True)
                    with open(os.path.join(FIXTURES, f"{name}.{kind}.json")) as f:
                        self.assertEqual(json.loads(out.stdout), json.load(f))


class NoPageSizeInThePageCode(unittest.TestCase):

    def test_the_width_is_declared_once_and_the_page_code_writes_none(self):
        sys.path.insert(0, HERE)
        from test_engine_plugin_hostd import ph
        with open(os.path.join(ROOT, ENGINE)) as f:
            self.assertEqual(len(re.findall(r"^SURFACE_WIDTH = \d+", f.read(), re.M)), 1, "one declaration")
        cls = ph.zynthian_engine_plugin_hostd
        for fn in (ph.panel_layout, cls.pages, cls.generate_ctrl_screens):
            code = re.sub(r"#.*", "", re.sub(r'""".*?"""', "", inspect.getsource(fn), flags=re.S))
            self.assertIsNone(re.search(r"(?<![\w.\"'])[2-9](?![\w.\"'])", code), f"a number in {fn.__name__}: a page size?")
            self.assertNotIn('"4"', code, fn.__name__)


ARMS = {
    "Easy dropped": [('        for page in cut[0]:\n            slots = []',
                      '        for page in cut[0]:\n            if page.get("sectionName") == "Easy":\n                continue\n            slots = []')],
    "the cut reordered after omx-panel": [('        for page in cut[0]:\n            slots = []',
                                           '        for page in sorted(cut[0], key=lambda p: p["pageName"], reverse=True):\n            slots = []')],
    "a hidden slot reflowed": [('slots.append(None)  # the slot stays, blank', 'pass')],
    "a surface page-size literal": [('str(width)', '"4"')],
    "a surface width ignored for a literal": [('width = width or SURFACE_WIDTH', 'width = 4')],
    "the base cutter asked again": [('self._ctrl_screens.append([name, [slot[0] if slot and slot[0] in zctrl_dict else None for slot in rows]])',
                                     'super().generate_ctrl_screens(zctrl_dict)')],
    "the merge drops a control a second page shows": [
        ('        result = []\n        for page in cut[0]:', '        result, seen = [], set()\n        for page in cut[0]:'),
        ('                    slots.append((key, lc.get("label") or dc.get("name"), None, dc))',
         '                    slots.append(None if key in seen else (key, lc.get("label") or dc.get("name"), None, dc))\n                    seen.add(key)')],
    "a key of the engine's own for the served symbol": [('return control.get("symbol") or str(control["id"])', 'return f"p{control[\'id\']}"')],
    "a hidden slot compressed out of the screen": [('self._ctrl_screens.append([name, [slot[0] if slot and slot[0] in zctrl_dict else None for slot in rows]])',
                                                   'self._ctrl_screens.append([name, [slot[0] for slot in rows if slot and slot[0] in zctrl_dict]])')],
}


def run_copy(mutations=()):
    with tempfile.TemporaryDirectory() as tmp:
        copy_core(tmp)
        path = os.path.join(tmp, ENGINE)
        with open(path) as f:
            code = f.read()
        for old, new in mutations:
            assert code.count(old) >= 1, f"the arm did not land: {old!r} is not in the engine"
            code = code.replace(old, new)
        with open(path, "w") as f:
            f.write(code)
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", os.path.join(tmp, "tests", "test_engine_plugin_hostd.py") + "::test_pages",
                               os.path.join(tmp, "tests", "test_engine_plugin_hostd.py") + "::test_easy",
                               os.path.join(tmp, "tests", "test_pages_conformance.py") + "::NoPageSizeInThePageCode"],
                              cwd=tmp, capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


class SabotageArms(unittest.TestCase):

    def test_the_unbroken_copy_is_green(self):
        r = run_copy()
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])

    def test_every_arm_turns_the_page_tests_red(self):
        for name, mutations in ARMS.items():
            with self.subTest(name):
                self.assertNotEqual(run_copy(mutations).returncode, 0, f"the arm '{name}' left the page tests green")


if __name__ == "__main__":
    unittest.main()
