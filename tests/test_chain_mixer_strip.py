# -*- coding: utf-8 -*-
#
# A chain that makes sound has its mixer strip (#21). The UI adds the strip when it creates such a chain, and the audio
# autoconnect routes a chain's outputs only through it: a snapshot that holds the chain without its strip (written by
# hand or by a tool) left a plugin-hostd piano with both outputs unconnected and the chain silent. Loading such a
# snapshot gives the chain its strip back, and a chain that still has none is named by the autoconnect, not left
# unconnected without a word. The chain manager's own set_state, on a real chain.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import sys
import types
import unittest
import importlib.util
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_refused_add as base  # noqa: E402

cm = base.cm
HERE = os.path.dirname(os.path.abspath(__file__))
UNROUTED = os.path.join(HERE, "..", "zynautoconnect", "unrouted_chains.py")
AUTOCONNECT = os.path.join(HERE, "..", "zynautoconnect", "zynthian_autoconnect.py")


class strip_engine(base.accepting_engine):
    """The audio mixer's engine, as far as a chain's strip needs it (started as ENGINE(state_manager))."""

    def __init__(self, state_manager):
        self.processors = []


class a_snapshot_chain_without_its_strip(unittest.TestCase):

    def setUp(self):
        base.refused_add.setUp(self)
        info = {"CAT": "Other", "ENABLED": False, "INDEX": 0, "URL": "", "UI": ""}
        self.man.engine_info["PH/Piano"]["ENGINE"] = base.accepting_engine
        self.man.engine_info["MI"] = dict(info, NAME="Mixer Channel Strip", TYPE="Audio Effect", ENGINE=strip_engine)
        self.man.engine_info["PH/Arp"] = dict(info, NAME="Arp", TYPE="MIDI Tool", ENGINE=base.accepting_engine)
        self.man.refresh_mixbus_sends = lambda: None

    def restore(self, slots):
        with mock.patch.object(cm.zynsigman, "send_queued"):
            self.man.set_state({1: {"title": "", "slots": slots}}, {}, merge=False)

    def strips(self):
        return [p for p in self.chain.get_processors() if p.eng_code == "MI"]

    def test_the_chain_gets_its_strip_back(self):
        self.restore([{"1000": "PH/Piano"}])
        self.assertIsNotNone(self.chain.zynmixer_proc, "a chain that makes sound has a strip")
        self.assertEqual(self.chain.zynmixer_proc.eng_code, "MI")
        self.assertTrue(self.chain.is_audio(), "so the audio autoconnect routes it")

    def test_the_strip_is_in_the_next_snapshot(self):
        self.restore([{"1000": "PH/Piano"}])
        saved = self.man.get_state()[1]["slots"]
        self.assertEqual(saved[0], {1000: "PH/Piano"})
        self.assertEqual([list(s.values()) for s in saved[1:]], [["MI"]], "the strip is saved after the synth")

    def test_the_load_says_it_added_one(self):
        with self.assertLogs(level="WARNING") as said:
            self.restore([{"1000": "PH/Piano"}])
        self.assertTrue(any("chain 1" in line and "mixer strip" in line for line in said.output), said.output)

    def test_a_chain_saved_with_its_strip_gets_no_second_one(self):
        self.restore([{"1000": "PH/Piano"}, {"1001": "MI"}])
        self.assertEqual([p.id for p in self.strips()], [1001])

    def test_a_chain_with_no_sound_source_gets_none(self):
        self.restore([{"1002": "PH/Arp"}])
        self.assertEqual(self.strips(), [], "a MIDI chain has no audio to route")
        self.assertIsNone(self.chain.zynmixer_proc)

    def test_a_synth_that_could_not_be_built_gets_none(self):
        self.man.engine_info["PH/Piano"]["ENGINE"] = base.refusing_engine
        self.restore([{"1000": "PH/Piano"}])
        self.assertEqual(self.strips(), [], "nothing makes sound yet")

    def test_no_busy_client_is_left_behind(self):
        self.restore([{"1000": "PH/Piano"}])
        self.assertFalse(self.man.state_manager.is_busy(), self.man.state_manager.busy)


def load_unrouted():
    """The module by its file: the autoconnect package imports JACK, which a test host does not have."""
    spec = importlib.util.spec_from_file_location("unrouted_chains", UNROUTED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chain(synth=True, strip=False):
    return types.SimpleNamespace(synth_slots=[[object()]] if synth else [], zynmixer_proc=object() if strip else None)


class the_autoconnect_names_a_chain_it_cannot_route(unittest.TestCase):

    def chains(self):
        return {1: chain(), 2: chain(strip=True), 3: chain(synth=False), 4: chain(synth=False, strip=True)}

    def test_a_sound_source_without_a_strip_is_named(self):
        said = set()
        with self.assertLogs(level="WARNING") as log:
            self.assertEqual(load_unrouted().say_unrouted(self.chains(), said), [1])
        self.assertEqual(len(log.output), 1, log.output)
        self.assertIn("chain 1", log.output[0])
        self.assertIn("mixer strip", log.output[0])

    def test_once_per_chain_not_at_every_autoconnect(self):
        module, said = load_unrouted(), set()
        with self.assertLogs(level="WARNING"):
            module.say_unrouted(self.chains(), said)
        with self.assertNoLogs(level="WARNING"):
            self.assertEqual(module.say_unrouted(self.chains(), said), [])

    def test_a_chain_that_gets_its_strip_and_loses_it_again_is_named_again(self):
        module, said = load_unrouted(), set()
        chains = self.chains()
        with self.assertLogs(level="WARNING"):
            module.say_unrouted(chains, said)
        chains[1].zynmixer_proc = object()
        module.say_unrouted(chains, said)
        chains[1].zynmixer_proc = None
        with self.assertLogs(level="WARNING"):
            self.assertEqual(module.say_unrouted(chains, said), [1])

    def test_the_audio_autoconnect_asks_with_the_chain_managers_chains(self):
        with open(AUTOCONNECT) as f:
            source = f.read()
        self.assertIn("say_unrouted(chain_manager.chains, unrouted_said)", source)


if __name__ == "__main__":
    unittest.main()
