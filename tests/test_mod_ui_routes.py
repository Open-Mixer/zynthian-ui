# -*- coding: utf-8 -*-
#
# Which MIDI routes the autoconnect leaves to MOD-UI. mod-host names the JACK client of a plugin effect_<n> and MOD-UI
# connects it itself, so the autoconnect takes its hands off every effect_ destination. plugin-hostd names its clients
# the same way, and those are chain processors: their routes are the autoconnect's, or the plugin gets no MIDI.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import types
import unittest
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "..", "zynautoconnect", "mod_ui_routes.py")
AUTOCONNECT = os.path.join(HERE, "..", "zynautoconnect", "zynthian_autoconnect.py")


def load():
    """The module by its file: the package imports JACK, which a test host does not have."""
    spec = importlib.util.spec_from_file_location("mod_ui_routes", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def processor(client, engine_client=None):
    """A chain processor as the autoconnect sees it: its client, and its engine's own client."""
    names = {False: client, True: engine_client or client}
    return types.SimpleNamespace(get_jackname=lambda engine=False: names[engine])


class test_mod_ui_routes(unittest.TestCase):

    def routes(self):
        return {
            "effect_3:midi_in": set(),  # a plugin MOD-UI added
            "effect_1000:midi_in": {"ZynMidiRouter:ch3_out"},  # plugin-hostd's, the synth of a chain
            "effect_1004:midi_in": {"ZynMidiRouter:ch0_out"},  # plugin-hostd's, the head of a worker
            "ZynMidiRouter:seq_in": {"zynsmf:midi_out"},
        }

    def test_a_chain_processor_keeps_its_route(self):
        routes = self.routes()
        load().drop_mod_ui_routes(routes, [processor("effect_1000"), processor("effect_1004", "effect_1005")])
        self.assertEqual(routes["effect_1000:midi_in"], {"ZynMidiRouter:ch3_out"})
        self.assertEqual(routes["effect_1004:midi_in"], {"ZynMidiRouter:ch0_out"})

    def test_a_plugin_of_mod_ui_is_left_to_mod_ui(self):
        routes = self.routes()
        load().drop_mod_ui_routes(routes, [processor("effect_1000")])
        self.assertNotIn("effect_3:midi_in", routes)
        self.assertNotIn("effect_1004:midi_in", routes, "no chain processor has this client now")
        self.assertEqual(routes["ZynMidiRouter:seq_in"], {"zynsmf:midi_out"}, "other destinations are not touched")

    def test_a_client_is_matched_whole(self):
        routes = {"effect_10:midi_in": set(), "effect_1000:midi_in": {"ZynMidiRouter:ch3_out"}}
        load().drop_mod_ui_routes(routes, [processor("effect_1000")])
        self.assertEqual(list(routes), ["effect_1000:midi_in"], "effect_10 is not effect_1000")

    def test_the_autoconnect_asks_with_its_chain_processors(self):
        with open(AUTOCONNECT) as f:
            source = f.read()
        self.assertIn("drop_mod_ui_routes(required_routes, chain_manager.processors.values(),", source)
        self.assertIn("hosted=(lambda client: hosted_instance(jclient, client, key) is not None)", source,
                      "the autoconnect tells plugin-hostd's clients by their instance key")
        self.assertNotIn('if dst.startswith("effect_"):\n            required_routes.pop(dst)', source,
                         "the rule that dropped every effect_ destination is gone")

    def test_a_plugin_hostd_client_keeps_its_route_by_its_key_not_its_name(self):
        """A client carrying the instance key is plugin-hostd's, whatever its name and whether or not
        a chain processor holds it now; an effect_ client without it is mod-host's, MOD-UI's to connect"""
        routes = {
            "effect_3:midi_in": set(),
            "effect_1004:midi_in": {"ZynMidiRouter:ch0_out"},
        }
        hosted = {"effect_1004"}
        load().drop_mod_ui_routes(routes, [processor("effect_1000")], hosted=lambda client: client in hosted)
        self.assertNotIn("effect_3:midi_in", routes)
        self.assertEqual(routes["effect_1004:midi_in"], {"ZynMidiRouter:ch0_out"})


if __name__ == "__main__":
    unittest.main()
