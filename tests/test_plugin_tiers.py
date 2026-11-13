# -*- coding: utf-8 -*-
#
# The plugin menus from plugin-db's answers: the answer asked through its command with the facts of here, the words a
# row shows, the sentences of the detail panel, what each bar offers, and the entries of a mixed catalogue in order.
# Every answer is one of plugin-db's own golden answers (plugin_db_stub). Plain `python3 -m unittest`.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import os
import sys
import types
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT]

if "zyngine" not in sys.modules:
    _pkg = types.ModuleType("zyngine")
    _pkg.__path__ = [os.path.join(ROOT, "zyngine")]
    sys.modules["zyngine"] = _pkg

from plugin_db import vocabulary as v  # noqa: E402
import plugin_db_stub  # noqa: E402
from plugin_db_stub import expect  # noqa: E402
from zyngine import zynthian_plugin_tiers as tiers  # noqa: E402
from zyngine import zynthian_plugin_qualification as qual  # noqa: E402

# (golden case, the words its row shows)
TAGS = [
    ("qualified", "qualified · shared · within"),
    ("qualified-over-the-line", "qualified · shared · over"),
    ("qualified-no-figure", "qualified · shared · unmeasured"),
    ("isolated-only", "isolated-only · alone · within"),
    ("conditions-no-cell", "conditions-unmet · alone"),
    ("measurement-pending", "unqualified · alone"),
    ("refused", "refused · not-loaded"),
    ("refused-warned-override", "refused · alone"),
    ("absent", "absent · not-loaded"),
]


class stub_case(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.commands = plugin_db_stub.commands(tmp.name)

    def qualification(self, answers, store=None):
        self.commands.set(answers)
        return qual.qualification(store, self.commands.plugin_db, self.commands.plugin_qualify)


class the_answer(stub_case):
    """An answer is plugin-db's, asked through its command with plugin-qualify's facts of here and jackd's settings."""

    def test_an_lv2_plugin_is_asked_by_its_uri_with_the_facts_of_here(self):
        q = self.qualification({"lv2:urn:q:fast": "qualified"})
        self.assertEqual(q.answer("urn:q:fast", 48000, 128), expect("qualified"))
        self.assertEqual(self.commands.calls(), [[
            "query", "--json", "lv2:urn:q:fast", "--machine-class", "rpi5", "--host", "plugin-hostd",
            "--host-version", "1.4.0", "--hosting-epoch", "2", "--rules", "rules-7", "--record-schema", "record-3",
            "--rate", "48000", "--quantum", "128"]])

    def test_a_clap_plugin_is_asked_by_its_id(self):
        q = self.qualification({"clap:org.surge-synth-team.surge-xt": "isolated-only"})
        url = "clap:/usr/local/lib/clap/Surge XT.clap#org.surge-synth-team.surge-xt"
        self.assertEqual(q.answer(url, 48000, 128)["state"], "isolated-only")
        self.assertEqual(self.commands.calls()[0][:3], ["query", "--json", "clap:org.surge-synth-team.surge-xt"])

    def test_a_named_store_is_the_one_asked(self):
        q = self.qualification({"lv2:urn:q:fast": "qualified"}, store="/var/lib/elsewhere")
        q.answer("urn:q:fast", 48000, 128)
        self.assertEqual(self.commands.calls()[0][:2], ["--store", "/var/lib/elsewhere"])

    def test_an_answer_is_asked_once_until_the_next_refresh(self):
        q = self.qualification({"lv2:urn:q:fast": "qualified"})
        q.answer("urn:q:fast", 48000, 128)
        q.answer("urn:q:fast", 48000, 128)
        self.assertEqual(len(self.commands.calls()), 1)
        q.answer("urn:q:fast", 96000, 128)
        self.assertEqual(len(self.commands.calls()), 2, "another rate is another question")
        self.commands.set({"lv2:urn:q:fast": "refused"})
        self.assertEqual(q.answer("urn:q:fast", 48000, 128)["state"], "qualified")
        self.assertEqual(q.refresh().answer("urn:q:fast", 48000, 128)["state"], "refused")

    def test_an_entry_the_store_does_not_hold_has_no_answer_and_none_is_made_up(self):
        q = self.qualification({})
        self.assertIsNone(q.answer("urn:q:unknown", 48000, 128))
        self.assertIsNone(q.answer("", 48000, 128))
        self.assertEqual(len(self.commands.calls()), 1, "an entry that is no plugin is not asked about")

    def test_facts_of_here_that_are_not_the_records_get_no_answer(self):
        wrong = dict(plugin_db_stub.here(), machineClass="x86-64")
        commands = plugin_db_stub.commands(self.commands.dir, {"lv2:urn:q:fast": "qualified"}, wrong)
        q = qual.qualification(None, commands.plugin_db, commands.plugin_qualify)
        self.assertIsNone(q.answer("urn:q:fast", 48000, 128), "the stand-in answers only for the facts its case is for")

    def test_without_the_facts_of_here_nothing_is_asked(self):
        q = qual.qualification(None, self.commands.plugin_db, os.path.join(self.commands.dir, "no-such-command"))
        with self.assertRaises(qual.HereError):
            q.answer("urn:q:fast", 48000, 128)
        with open(self.commands.plugin_qualify, "w") as f:
            f.write("#!/bin/sh\necho 'unknown command here' >&2\nexit 2\n")
        q = self.qualification({"lv2:urn:q:fast": "qualified"})
        with self.assertRaises(qual.HereError) as refused:
            q.answer("urn:q:fast", 48000, 128)
        self.assertIn("unknown command here", str(refused.exception))
        self.assertEqual(self.commands.calls(), [])

    def test_the_addresses(self):
        self.assertEqual(qual.address("http://lsp-plug.in/plugins/lv2/art_delay_stereo"),
                         "lv2:http://lsp-plug.in/plugins/lv2/art_delay_stereo")
        self.assertEqual(qual.address("clap:/usr/lib/clap/lsp-plugins.clap#in.lsp-plug.art_delay_stereo"),
                         "clap:in.lsp-plug.art_delay_stereo")
        self.assertIsNone(qual.address(""))
        self.assertIsNone(qual.address("clap:/usr/lib/clap/x.clap#"))


class the_words(unittest.TestCase):

    def test_a_row_shows_the_state_where_it_runs_and_where_its_latency_stands(self):
        for case, words in TAGS:
            with self.subTest(case=case):
                self.assertEqual(tiers.tag(expect(case)), words)

    def test_the_detail_panel_says_the_answer_in_the_owners_sentences(self):
        self.assertEqual(tiers.answer_text(expect("qualified"), "en"),
                         "Qualified: it runs as its record allows. Its record allows a shared worker. "
                         "Runs in a shared worker. Measured on this machine. in-process "
                         "Latency within the line. 1.5 ms / 3 ms (48000 Hz, 128)")
        self.assertEqual(tiers.answer_text(expect("refused"), "en"),
                         "Refused: it is not loaded. Its record says refused. "
                         "Not loaded: an effect passes audio through, an instrument is silent. Measured on this machine.")
        self.assertEqual(tiers.answer_text(expect("qualified-no-figure"), "en").split(". ")[-1],
                         "in-process Latency not measured.")
        self.assertTrue(tiers.answer_text(expect("qualified-no-line"), "en").endswith("1.5 ms (48000 Hz, 128)"))
        self.assertIsNone(tiers.answer_text(None))

    def test_the_sentences_are_read_in_the_devices_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "ca.json"), "w") as f:
                f.write('{"messages": {"PLUGIN_DB_STATES.refused": "Refusat: no es carrega."}}')
            with mock.patch.object(sys.modules["plugin_db.text"], "CATALOGS", tmp), \
                    mock.patch.dict(os.environ, {"LC_ALL": "ca_ES.UTF-8"}):
                said = tiers.answer_text(expect("refused"))
        self.assertTrue(said.startswith("Refusat: no es carrega. Its record says refused."), said)

    def test_no_word_of_plugin_db_is_written_again_in_the_two_modules(self):
        owned = set()
        for words in (v.states, v.runs, v.latency, v.reasons, v.sources, v.bar, v.pin_verdicts):
            owned |= set(words.values())
        for name in ("zynthian_plugin_tiers.py", "zynthian_plugin_qualification.py"):
            with open(os.path.join(ROOT, "zyngine", name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            docs = {id(n.body[0].value) for n in ast.walk(tree)
                    if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                    and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            again = sorted({n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                            and id(n) not in docs and n.value in owned})
            self.assertEqual(again, [], f"{name} writes plugin-db's words itself")


def info(name, url, title=None, **more):
    return {"NAME": name, "TITLE": title or f"{name} (PH)", "URL": url, **more}


class the_bar(unittest.TestCase):

    def test_what_each_bar_offers(self):
        cases = ("qualified", "isolated-only", "conditions-no-cell", "measurement-pending", "refused", "absent")
        offered = lambda bar: [c for c in cases if tiers.offered(expect(c), bar)]
        self.assertEqual(offered("qualified-only"), ["qualified"])
        self.assertEqual(offered("warn-on-crashes"), ["qualified", "isolated-only", "conditions-no-cell", "measurement-pending"])
        self.assertEqual(offered("load-all"), list(cases))

    def test_the_bars_are_plugin_dbs_three_words(self):
        self.assertEqual(tiers.BARS, ("qualified-only", "warn-on-crashes", "load-all"))
        self.assertEqual(set(tiers.BAR_TITLES), set(tiers.BARS))
        self.assertEqual(tiers.DEFAULT_BAR, "warn-on-crashes")


class the_menu(unittest.TestCase):

    ANSWERS = {"urn:q:pending": "measurement-pending", "urn:q:refused": "refused", "urn:q:alone": "isolated-only",
               "urn:q:fast": "qualified", "urn:q:slow": "qualified-over-the-line", "urn:q:gone": "absent",
               "urn:q:nocell": "conditions-no-cell"}

    def engines(self):
        return {"PH/Pending": info("Pending", "urn:q:pending"), "PH/Refused": info("Refused Amp", "urn:q:refused"),
                "ZY": {"TITLE": "ZynAddSubFX"}, "PH/Alone": info("Alone Synth", "urn:q:alone"),
                "PH/Slow": info("Linear EQ", "urn:q:slow"), "PH/Fast": info("Fast Comp", "urn:q:fast"),
                "PH/Gone": info("Gone", "urn:q:gone"), "PH/NoCell": info("No Cell", "urn:q:nocell"),
                "PH/Unknown": info("Unknown", "urn:q:unknown"),
                "JV/Refused": info("Refused Amp", "urn:q:refused", title="Refused Amp")}

    def rows(self, engines=None, answers=None, **options):
        answers = self.ANSWERS if answers is None else answers
        answer_of = lambda url: expect(answers[url]) if url in answers else None
        return tiers.menu_entries(self.engines() if engines is None else engines, answer_of, **options)

    def test_by_state_the_ones_that_run_first_and_the_ones_not_loaded_left_out_by_default(self):
        self.assertEqual(self.rows(), [
            ("PH/Slow", "Linear EQ (PH)  qualified · shared · over", False),
            ("PH/Fast", "Fast Comp (PH)  qualified · shared · within", False),
            ("PH/Alone", "Alone Synth (PH)  isolated-only · alone · within", False),
            ("PH/NoCell", "No Cell (PH)  conditions-unmet · alone", False),
            ("PH/Pending", "Pending (PH)  unqualified · alone", False),
            ("ZY", "ZynAddSubFX", False),
            ("PH/Unknown", "Unknown (PH)", False),
            ("JV/Refused", "Refused Amp", False),
        ])

    def test_load_all_lists_the_refused_and_the_absent_marked_after_the_others(self):
        rows = self.rows(bar="load-all")
        self.assertEqual(rows[-2:], [("PH/Refused", "Refused Amp (PH)  refused · not-loaded", tiers.BELOW),
                                     ("PH/Gone", "Gone (PH)  absent · not-loaded", tiers.BELOW)])
        self.assertEqual(len(rows), 10, "the jalv row of the refused plugin gives way to no one: it is another engine")
        self.assertIn(("JV/Refused", "Refused Amp", False), rows)

    def test_qualified_only_lists_the_qualified_and_the_rows_plugin_db_does_not_judge(self):
        self.assertEqual([key for key, _, _ in self.rows(bar="qualified-only")], ["PH/Slow", "PH/Fast", "ZY", "JV/Refused"])

    def test_a_jalv_row_is_never_asked_about(self):
        asked = []
        tiers.menu_entries(self.engines(), lambda url: asked.append(url), bar="load-all")
        self.assertNotIn("urn:q:refused", asked[1:2] and [u for u in asked if asked.count(u) > 1])
        self.assertEqual(asked.count("urn:q:refused"), 1, "once, for the plugin-hostd row")

    def test_by_latency_the_rows_with_a_figure_first(self):
        rows = self.rows(order="latency", bar="load-all")
        self.assertEqual([key for key, _, _ in rows][:3], ["PH/Alone", "PH/Fast", "PH/Slow"])
        self.assertEqual([key for key, _, _ in rows][-2:], ["PH/Gone", "PH/Refused"], "the ones not loaded stay last")

    def test_by_name(self):
        keys = [key for key, _, _ in self.rows(order="name")]
        self.assertEqual(keys, ["PH/Alone", "PH/Fast", "PH/Slow", "PH/NoCell", "PH/Pending", "JV/Refused", "PH/Unknown", "ZY"])

    def test_hosted_only_keeps_the_plugin_hostd_rows(self):
        self.assertEqual({key.split("/")[0] for key, _, _ in self.rows(hosted_only=True)}, {"PH"})

    def test_an_entry_that_does_not_load_is_last_and_greyed(self):
        engines = self.engines()
        engines["PH/Fast"]["NOT_WORKING"] = "does not load"
        rows = self.rows(engines, bar="load-all")
        self.assertEqual(rows[-1], ("PH/Fast", "Fast Comp (PH)  not working · does not load", True))

    def test_a_plugin_in_two_formats_is_one_row_the_better_placed(self):
        clap = "clap:/usr/lib/clap/Kars.clap#studio.kx.distrho.Kars"
        engines = {"PH/Kars": info("Kars", "urn:kars"), "PH/" + clap: info("Kars", clap)}
        both = {"urn:kars": "qualified", clap: "qualified"}
        self.assertEqual([key for key, _, _ in self.rows(engines, both)], ["PH/" + clap], "CLAP before LV2 on a tie")
        better_lv2 = {"urn:kars": "qualified", clap: "measurement-pending"}
        self.assertEqual([key for key, _, _ in self.rows(engines, better_lv2)], ["PH/Kars"])
        self.assertEqual(len(self.rows({"PH/a": info("Kars", "urn:a"), "PH/b": info("Kars", "urn:b")}, {})), 2,
                         "two plugins of one format that share a name stay two rows")


if __name__ == "__main__":
    unittest.main()
