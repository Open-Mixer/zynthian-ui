# -*- coding: utf-8 -*-
#
# A plugin-hostd chain survives a restart of the UI. A snapshot restore that cannot build a processor (the daemon was
# not answering yet, the plugin was refused) leaves it out of the chain, and must not leave it out of the next
# snapshot: the slot is written back as it was, with the reason shown, until the chain is removed or the processor is
# built. And the daemon the UI starts is answering by the time its start returns.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_engine_plugin_hostd import ph, plugin_hostd_case, START_STUB  # noqa: E402
import test_refused_add as base  # noqa: E402

cm = base.cm


class held_back_engine(base.refusing_engine):
    """The engine of a UI that starts before plugin-hostd answers."""

    def set_extended_config(self, xconfig):
        pass

    def add_processor(self, processor):
        raise ph.plugin_hostd_down("no daemon on port 5570 and the start script failed: Connection refused")


class a_chain_that_could_not_be_built(unittest.TestCase):

    def setUp(self):
        base.refused_add.setUp(self)
        self.man.engine_info["PH/Piano"]["ENGINE"] = held_back_engine
        self.state = {1: {"title": "", "slots": [{"1000": "PH/Piano"}]}}

    def restore(self):
        with mock.patch.object(cm.zynsigman, "send_queued") as send:
            self.man.set_state(self.state, {"PH#1000": {"state": "x"}}, merge=False)
        return send

    def slots(self):
        return self.man.get_state()[1]["slots"]

    def test_the_slot_is_saved_again_when_the_daemon_was_held_back(self):
        self.restore()
        self.assertEqual(self.chain.get_processors(), [], "nothing could be built")
        self.assertEqual(self.slots(), [{1000: "PH/Piano"}], "the snapshot taken now still holds the plugin")

    def test_the_reason_is_said(self):
        send = self.restore()
        messages = [c.kwargs.get("message") for c in send.call_args_list if c.kwargs.get("message")]
        self.assertEqual(len(messages), 1)
        self.assertIn("Connection refused", messages[0])
        self.assertIn("Connection refused", self.man.unbuilt["1000"]["reason"])

    def test_it_keeps_its_place_among_the_slots_that_were_built(self):
        self.state = {1: {"slots": [{"1000": "PH/Piano"}, {"1001": "PH/Ok"}]}}
        self.restore()
        self.assertEqual([p.id for p in self.chain.get_processors()], [1001])
        self.assertEqual(self.slots(), [{1000: "PH/Piano"}, {1001: "PH/Ok"}])

    def test_its_engine_configuration_is_kept_for_the_state_manager_to_write(self):
        self.restore()
        self.assertEqual(self.man.unbuilt["1000"]["eng_config"], {"state": "x"})

    def test_building_it_later_ends_the_wait(self):
        self.restore()
        self.man.engine_info["PH/Piano"]["ENGINE"] = base.accepting_engine
        self.assertIsNotNone(self.man.add_processor(1, "PH/Piano", proc_id=1000))
        self.assertNotIn("1000", self.man.unbuilt)
        self.assertEqual(self.slots(), [{1000: "PH/Piano"}], "once, as the chain's own slot")

    def test_removing_the_chain_is_the_users_word_and_it_is_not_written_again(self):
        self.restore()
        self.man.remove_chain = lambda chain_id, *a, **k: cm.zynthian_chain_manager.remove_chain(self.man, chain_id, *a, **k)
        self.man.forget_unbuilt(1)
        self.assertEqual(self.slots(), [])

    def test_loading_another_snapshot_forgets_what_the_first_one_could_not_build(self):
        self.restore()
        self.state = {1: {"slots": []}}
        self.restore()
        self.assertEqual(self.man.unbuilt, {})
        self.assertEqual(self.slots(), [])


class a_daemon_that_is_not_listening_when_its_start_returns(plugin_hostd_case):

    def test_the_add_waits_for_it_and_the_chain_is_built(self):
        ph.daemon.start_script = START_STUB
        os.environ["START_STUB_LATE"] = "0.6"
        self.addCleanup(os.environ.pop, "START_STUB_LATE", None)
        chain = self.chain()
        proc = self.add(chain, "PH/Amp")
        self.assertIsNotNone(proc.engine.instance, "the add did not meet a refused connection")
        self.remove(chain, proc)
        if ph.daemon.pid:
            try:
                os.kill(ph.daemon.pid, 15)
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    unittest.main()
