# -*- coding: utf-8 -*-
#
# A curve is bound by terms <role>=<symbol>:<unit> (curve_bind, plugin-hostd-protocol's host-curve.c), and the
# protocol reads the unit as one of the standard ids omx-dsp names for its curve words (from plugin-hostd-protocol 0.8.0,
# its 116e042: OMX_CURVE_UNITS_STANDARD, the `standard` list of CURVE_UNITS in the curve.json omx-dsp-contract installs;
# the lower-case curve words hz, db are no unit there and answer curve-unit-refused): a term in another word is refused
# and no curve is drawn. curve_bind_line writes the unit describe gives the role, with omx-panel 0.16 a standard unit
# id of omx-contract's param domain (Hz, dB, percent: omx-panel#180) (#107).
#
#  - the recorded describe of omx-panel's scanned-clap-omx-eq8 descriptor by omx-panel lane/sort-pass-omx-panel 2db00a9
#    (fixtures/omx_panel/scanned-clap-omx-eq8.describe.omx-panel-2db00a9.json, its stdout byte for byte);
#  - with OMX_PANEL_REAL, the describe of the same descriptor by the omx-panel this run has.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import json
import os
import shlex
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures", "omx_panel")
DESCRIPTOR = os.path.join(FIXTURES, "scanned-clap-omx-eq8.descriptor.json")
RECORDED = os.path.join(FIXTURES, "scanned-clap-omx-eq8.describe.omx-panel-2db00a9.json")

_spec = importlib.util.spec_from_file_location("panel_view_units", os.path.join(ROOT, "zyngine", "zynthian_omx_panel_view.py"))
view = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(view)


def curve_unit_words():
    """The units curve_bind takes: the standard ids of omx-dsp's curve unit words, as its contract package installs
    them."""
    root = (os.environ.get("OMX_CONTRACT_PATH") or view.CONTRACT_PATH).split(":")[0]
    with open(os.path.join(root, "3", "omx-dsp", "primitives", "curve.json")) as f:
        return set(json.load(f)["CURVE_UNITS"]["standard"])


def units_of(line):
    """The unit word of each term of a curve_bind line: {term: unit}."""
    out = {}
    for term in line.split()[5:]:
        unit = term.split("@", 1)[0].partition(":")[2]
        out[term] = unit or "none"
    return out


class CurveTermsAreInTheUnitsCurveBindTakes(unittest.TestCase):

    def check(self, description):
        words = curve_unit_words()
        lines = [view.curve_bind_line(3, i, description) for i in range(len(description.get("displays") or []))]
        lines = [line for line in lines if line]
        self.assertTrue(lines, "the eq's describe has a curve display")
        for line in lines:
            refused = {t: u for t, u in units_of(line).items() if u not in words}
            self.assertEqual(refused, {}, f"terms curve_bind refuses (it takes: {sorted(words)}): {line}")

    def test_the_recorded_describe_of_omx_panel_0_16_binds_in_the_units_curve_bind_takes(self):
        with open(RECORDED) as f:
            self.check(json.load(f)["description"])

    @unittest.skipUnless(os.environ.get("OMX_PANEL_REAL"), "OMX_PANEL_REAL is 'node path/to/omx-panel.mjs', the real command")
    def test_the_real_describe_binds_in_the_units_curve_bind_takes(self):
        real = shlex.split(os.environ["OMX_PANEL_REAL"])
        out = subprocess.run(real + ["describe", "--descriptor", DESCRIPTOR], capture_output=True, text=True, check=True)
        self.check(json.loads(out.stdout)["description"])


if __name__ == "__main__":
    unittest.main()
