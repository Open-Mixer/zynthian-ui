# -*- coding: utf-8 -*-
#
# The engine's side of a panel's drawn view (bars, curves and meters drawn by omx-panel's renderer): which plugins get
# the panel's own screen, the curve plugin-hostd computes for a display (curve_bind once, curve_points each time, bound
# again once after a respawn lost the binding), and a meter asked once per feedback connection. On the fake daemon of
# test_engine_plugin_hostd, with omx-panel's stub answering `describe --layout` from the files written here.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import json
import os
import shutil
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_engine_plugin_hostd import FIXTURES, plugin_hostd_case, ph  # noqa: E402

PANEL_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "omx_panel")


class drawn_view(plugin_hostd_case):

    def drawn_plugin(self, layout=True, panel=None):
        """urn:test:big (parameters p0..p9) described as a compressor: its description binds threshold to p0 and ratio
        to p1 for a transfer curve, and its layout (omx-comp's) has that curve and the meters."""
        base = os.path.join(self.tmp, "comp")
        shutil.copy(os.path.join(FIXTURES, "big.descriptor.json"), base + ".descriptor.json")
        shutil.copy(os.path.join(FIXTURES, "big.pages4.json"), base + ".pages4.json")
        with open(os.path.join(FIXTURES, "big.describe.json")) as f:
            described = json.load(f)
        with open(os.path.join(PANEL_FIXTURES, "omx-comp.json")) as f:
            comp = json.load(f)
        described["description"].update(family="dynamics", displays=comp["description"]["displays"], roles=[
            {"role": "threshold", "index": 0, "symbol": "p0", "unit": "db"},
            {"role": "ratio", "index": 0, "symbol": "p1", "unit": "ratio"},
            {"role": "attack", "index": 0, "symbol": "p2", "unit": "ms"}])
        with open(base + ".describe.json", "w") as f:
            json.dump(described, f)
        if layout:
            with open(base + ".layout.json", "w") as f:
                json.dump(comp["layout"], f)
        panels = {}
        if panel is not None:  # the document plugin-hostd-probe panel wrote, filed beside the descriptor
            panels["urn:test:big"] = os.path.join(self.tmp, "panels", "comp.json")
            os.makedirs(os.path.dirname(panels["urn:test:big"]), exist_ok=True)
            with open(panels["urn:test:big"], "w") as f:
                json.dump(panel, f)
        self.describes = os.path.join(self.tmp, "omx-panel.log")
        os.environ["OMX_PANEL_STUB_LOG"] = self.describes
        self.addCleanup(os.environ.pop, "OMX_PANEL_STUB_LOG", None)
        fake = self.serve(descriptors={"urn:test:big": base + ".descriptor.json"}, panels=panels)
        return fake, self.add(self.chain(), "PH/Big")

    def describe_lines(self):
        with open(self.describes) as f:
            return [line.split() for line in f if line.startswith("describe")]

    def test_the_plugins_own_panel_is_given_to_describe(self):
        # plugin-hostd files the plugin's own panel (panel_get): its family, roles and displays are the plugin's, and
        # omx-panel lays them out only when describe is given them with --panel
        declared = {"family": "dynamics", "sections": [{"key": "comp", "label": "Comp"}], "controls": [],
                    "roles": [{"role": "threshold", "index": 0, "paramId": 0}],
                    "displays": [{"kind": "transfer_curve", "section": 0, "source": "family"}]}
        self.drawn_plugin(panel={"plugin": {"format": "lv2", "id": "urn:test:big"}, "panel": declared})
        lines = self.describe_lines()
        self.assertTrue(lines, "omx-panel was run")
        for words in lines:
            self.assertIn("--panel", words, f"describe is given the plugin's panel: {' '.join(words)}")
            with open(words[words.index("--panel") + 1]) as f:
                self.assertEqual(json.load(f), declared, "the panel itself, as omx-panel's --panel reads it")

    def gr_bar(self, layout):
        """The meters the gain-reduction bar of a drawn layout reads, by symbol: its ids index the layout's meters."""
        bar = [d for d in layout["displays"] if d["kind"] == "gain_reduction_bar"][0]
        return [layout["meters"][k]["symbol"] if k is not None else None for k in bar["meters"]]

    def test_the_gr_bar_reads_meter_0_of_describes_meters_while_the_panel_carries_none(self):
        declared = {"family": "dynamics", "sections": [{"key": "comp", "label": "Comp"}], "controls": [], "roles": [],
                    "displays": [{"kind": "gain_reduction_bar", "section": 0, "source": "meters", "meterIds": [0, None]}]}
        _, proc = self.drawn_plugin(panel={"plugin": {"format": "lv2", "id": "urn:test:big"}, "panel": declared})
        layout = proc.engine.drawn[0]
        self.assertEqual([m["symbol"] for m in layout["meters"]], ["compGr", "compIn", "compOut", "compKey"])
        self.assertEqual(self.gr_bar(layout), ["compGr", None])

    def test_the_meters_the_panel_reply_carries_are_the_ones_drawn(self):
        # plugin-hostd's panel reply carries the plugin's meters (clap.meters/1) with its displays' meter ids: those
        # are the meters drawn, the GR bar's meter 0 the panel's own first, each with describe's facts of it
        declared = {"family": "dynamics", "sections": [{"key": "comp", "label": "Comp"}], "controls": [], "roles": [],
                    "displays": [{"kind": "gain_reduction_bar", "section": 0, "source": "meters", "meterIds": [0, None]}],
                    "meters": [{"symbol": "compGr", "kind": "gain-reduction"}, {"symbol": "compOut", "kind": "level"}]}
        _, proc = self.drawn_plugin(panel={"plugin": {"format": "lv2", "id": "urn:test:big"}, "panel": declared})
        layout = proc.engine.drawn[0]
        self.assertEqual([m["symbol"] for m in layout["meters"]], ["compGr", "compOut"])
        self.assertEqual(layout["meters"][0]["unit"], "dB", "describe's facts of the meter kept")
        self.assertEqual(self.gr_bar(layout), ["compGr", None])

    def test_a_panel_meter_id_beyond_its_meters_draws_no_bar_meter(self):
        declared = {"family": "dynamics", "sections": [{"key": "comp", "label": "Comp"}], "controls": [], "roles": [],
                    "displays": [{"kind": "gain_reduction_bar", "section": 0, "source": "meters", "meterIds": [3, None]}],
                    "meters": [{"symbol": "compGr", "kind": "gain-reduction"}]}
        with self.assertLogs(level="WARNING") as logs:
            _, proc = self.drawn_plugin(panel={"plugin": {"format": "lv2", "id": "urn:test:big"}, "panel": declared})
        self.assertEqual(self.gr_bar(proc.engine.drawn[0]), [None, None])
        self.assertTrue([m for m in logs.output if "meter 3" in m])

    def test_a_plugin_with_no_panel_of_its_own_is_described_from_its_descriptor(self):
        self.drawn_plugin()
        self.assertTrue(self.describe_lines())
        self.assertFalse([w for w in self.describe_lines() if "--panel" in w])

    def test_a_panel_document_holding_no_panel_gives_describe_none(self):
        # plugin-hostd-probe panel answers "panel": null for a plugin that declares none (eq8)
        self.drawn_plugin(panel={"plugin": {"format": "lv2", "id": "urn:test:big"}, "panel": None})
        self.assertFalse([w for w in self.describe_lines() if "--panel" in w])

    def test_a_panel_with_a_curve_or_a_meter_gets_its_own_screen(self):
        _, proc = self.drawn_plugin()
        self.assertEqual(os.path.basename(proc.engine.custom_gui_fpath), "zynthian_widget_omx_panel.py")
        self.assertTrue(os.path.exists(proc.engine.custom_gui_fpath))

    def test_a_panel_with_none_keeps_the_controller_screens(self):
        _, proc = self.drawn_plugin(layout=False)  # the stub's layout for no record has no bar group, display or meter
        self.assertIsNone(proc.engine.custom_gui_fpath)

    def test_an_omx_panel_without_describe_layout_is_said_once(self):
        os.environ["OMX_PANEL_STUB_NO_LAYOUT"] = "1"
        self.addCleanup(os.environ.pop, "OMX_PANEL_STUB_NO_LAYOUT", None)
        with self.assertLogs(level="INFO") as logs:
            _, proc = self.drawn_plugin()
        self.assertIsNone(proc.engine.custom_gui_fpath)
        self.assertEqual(sum("describe --layout" in m for m in logs.output), 1)

    def test_the_curve_is_bound_once_by_its_curve_roles_and_read_each_time(self):
        fake, proc = self.drawn_plugin()
        engine = proc.engine
        fake.params[engine.instance]["p0"] = -18.0
        self.assertEqual(engine.curve(0), [(20.0, -18.0), (20000.0, -18.0)])
        self.assertEqual(engine.curve(0), [(20.0, -18.0), (20000.0, -18.0)])
        binds = [l for l in fake.lines if l.startswith("curve_bind")]
        self.assertEqual(binds, [f"curve_bind {engine.instance} 0 transfer_curve dynamics threshold=p0:db ratio=p1:ratio"],
                         "once, and attack is no curve role")
        self.assertEqual(len([l for l in fake.lines if l.startswith("curve_points")]), 2)

    def test_a_binding_the_daemon_lost_is_made_again_once(self):
        fake, proc = self.drawn_plugin()
        engine = proc.engine
        engine.curve(0)
        fake.forget_curves()
        self.assertEqual(len(engine.curve(0)), 2, "bound again and drawn")
        self.assertEqual(len([l for l in fake.lines if l.startswith("curve_bind")]), 2)

    def test_a_display_that_is_no_curve_asks_nothing(self):
        fake, proc = self.drawn_plugin()
        proc.engine.drawn[1]["displays"] = [{"kind": "gain_reduction_bar"}]
        self.assertEqual(proc.engine.curve(0), [])
        self.assertFalse([l for l in fake.lines if l.startswith("curve_")])

    def test_a_meter_is_monitored_once_per_feedback_connection(self):
        fake, proc = self.drawn_plugin()
        engine, fb = proc.engine, ph.daemon.client.feedback
        fb.sock, fb.generation = object(), 7  # a feedback connection, as connect leaves it
        self.addCleanup(setattr, fb, "sock", None)
        fb.values[(engine.instance, "compGr")] = -4.0
        self.assertEqual(engine.meter("compGr"), -4.0)
        self.assertEqual(engine.meter("compGr"), -4.0)
        self.assertEqual(fake.monitors, [(engine.instance, "compGr")])
        fb.generation = 8  # the connection came back: its monitors went with the old one
        engine.meter("compGr")
        self.assertEqual(fake.monitors, [(engine.instance, "compGr")] * 2)

    def test_no_feedback_connection_asks_no_monitor(self):
        fake, proc = self.drawn_plugin()
        self.assertIsNone(proc.engine.meter("compGr"))
        self.assertEqual(fake.monitors, [])


if __name__ == "__main__":
    unittest.main()
