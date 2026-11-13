# -*- coding: utf-8 -*-
#
# What a chain shows for its plugin-hostd members. The daemon's JACK client of a plugin is effect_<instance>, and a
# worker runs several members in one client; neither is a name for the screen. The chain view, the chain's title and
# the breadcrumb take the plugin's name from the catalogue. The chain and its processors are the real ones; the daemon
# is the fake.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_engine_plugin_hostd as phtest  # noqa: E402

AMP = "PH/Amp"
CLAP = "PH/clap:/usr/lib/clap/lsp-plugins.clap#in.lsp-plug.limiter_mono"


class test_member_names(phtest.plugin_hostd_case):

    def shown(self, proc):
        """Every text the screens take from a processor: the chain view's node, the breadcrumb, the preset path."""
        return (proc.get_name(), proc.get_basepath(), proc.get_presetpath())

    def test_a_member_shows_the_plugin_name(self):
        self.serve()
        chain = self.chain()
        proc = self.add(chain, AMP)
        self.assertEqual(proc.get_jackname(), "effect_1000", "the client is the daemon's")
        self.assertEqual(proc.get_name(), self.info[AMP]["NAME"])
        self.assertEqual(chain.get_name(), "1#" + self.info[AMP]["NAME"], "the chain is titled by its first member")
        for text in self.shown(proc):
            self.assertNotIn("effect_", text)

    def test_members_a_worker_runs_in_one_client_keep_their_own_names(self):
        self.serve()
        chain = self.chain()
        a, b = self.add(chain, AMP), self.add(chain, CLAP)
        self.assertEqual({a.get_jackname(), b.get_jackname()}, {"effect_1000"}, "one client for the run")
        self.assertEqual((a.get_name(), b.get_name()), (self.info[AMP]["NAME"], self.info[CLAP]["NAME"]))
        self.assertNotEqual(a.get_name(), b.get_name())
        for text in self.shown(a) + self.shown(b) + (chain.get_name(),):
            self.assertNotIn("effect_", text)


if __name__ == "__main__":
    phtest.unittest.main()
