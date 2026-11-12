# -*- coding: utf-8 -*-
#
# The engine selection screen's own methods (zyngui/zynthian_gui_engine.py) building a plugin menu
# from plugin-db's answers (its golden ones, plugin_db_stub), and toggling a PH entry in its enable view.
# tkinter and the base screens are stand-ins; the screen code is the real one.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import sys
import types
import logging
import tempfile
import unittest
import importlib.util
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT]

if "zyngine" not in sys.modules:
    _pkg = types.ModuleType("zyngine")
    _pkg.__path__ = [os.path.join(ROOT, "zyngine")]
    sys.modules["zyngine"] = _pkg
import plugin_db_stub  # noqa: E402
from zyngine import zynthian_plugin_qualification as qual  # noqa: E402
from zyngine import zynthian_plugin_tiers as tiers  # noqa: E402
import test_engine_plugin_hostd  # noqa: E402,F401  the stand-ins of the native libraries, for the engine the screen imports


def stand_in(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


class selector:
    def __init__(self, *args):
        pass

    def fill_list(self):
        self.filled = list(self.list_data)


def load_screen():
    gui_config = stand_in("zyngui.zynthian_gui_config", color_tx_off="#grey", color_warn="#warn", color_panel_bg="#bg",
                          color_panel_tx="#tx", layout={"ctrl_order": []})
    modules = {
        "tkinter": stand_in("tkinter", END="end"),
        "zyngui": stand_in("zyngui", __path__=[], zynthian_gui_config=gui_config),
        "zyngui.zynthian_gui_config": gui_config,
        "zyngui.zynthian_gui_base": stand_in("zyngui.zynthian_gui_base", zynthian_gui_base=object),
        "zyngui.zynthian_gui_selector": stand_in("zyngui.zynthian_gui_selector", zynthian_gui_selector=selector),
        "zyngui.zynthian_gui_controller": stand_in("zyngui.zynthian_gui_controller", zynthian_gui_controller=object),
        "zyngine.zynthian_lv2": stand_in("zyngine.zynthian_lv2", engines_by_type={}),
    }
    with mock.patch.dict(sys.modules, modules), \
            mock.patch.object(sys.modules["zyngine"], "zynthian_lv2", modules["zyngine.zynthian_lv2"], create=True):
        spec = importlib.util.spec_from_file_location("zynthian_gui_engine_under_test",
                                                      os.path.join(ROOT, "zyngui", "zynthian_gui_engine.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


screen_module = load_screen()


# the golden answer of plugin-db each plugin of the menu is given
ANSWERS = {"lv2:urn:q:slow": "qualified-over-the-line", "lv2:urn:q:fast": "qualified", "lv2:urn:q:refused": "refused",
           "lv2:urn:q:pending": "measurement-pending"}
FAST = "Fast Comp (PH)  qualified · shared · within"
SLOW = "Linear EQ (PH)  qualified · shared · over"
REFUSED = "Refused Amp (PH)  refused · not-loaded"


def info(name, url, enabled=True, title=None):
    return {"NAME": name, "TITLE": title or f"{name} (PH)", "TYPE": "Audio Effect", "CAT": "Dynamics", "URL": url,
            "ENABLED": enabled, "EDIT": 0}


class engine_menu(unittest.TestCase):

    def setUp(self):
        self.engines = {"PH/Slow": info("Linear EQ", "urn:q:slow"), "PH/Fast": info("Fast Comp", "urn:q:fast"),
                        "PH/Refused": info("Refused Amp", "urn:q:refused"),
                        "PH/Pending": info("New Delay", "urn:q:pending")}
        self.by_cat = {"Dynamics": dict(self.engines), "Delay": {"PH/Pending": self.engines["PH/Pending"]}}
        self.by_cat["Dynamics"].pop("PH/Pending")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.commands = plugin_db_stub.commands(tmp.name, ANSWERS)
        s = object.__new__(screen_module.zynthian_gui_engine)
        s.chain_manager = mock.MagicMock()
        s.chain_manager.engine_info = self.engines
        s.chain_manager.filtered_engines_by_cat.side_effect = lambda t, all: {c: dict(e) for c, e in self.by_cat.items()}
        s.zyngui = mock.MagicMock()
        s.zyngui.modify_chain_status = {"type": "MIDI Synth"}
        s.zyngui.state_manager.get_jackd_samplerate.return_value = 48000
        s.zyngui.state_manager.get_jackd_blocksize.return_value = 256
        s.qualification = qual.qualification(None, self.commands.plugin_db, self.commands.plugin_qualify)
        s.listbox, s.listbox2 = mock.MagicMock(), mock.MagicMock()
        s.lb2_fg = s.lb2_bg = "#c"
        s.cat_index, s.show_all, s.engine_info_dirty, s.index, s.context_index = 0, False, False, 0, {}
        s.list_order, s.hosted_only, s.bar = "state", False, "warn-on-crashes"
        s.update_list = lambda: None
        self.screen = s

    def build(self, bar="warn-on-crashes"):
        self.screen.bar = bar
        self.screen.get_engines_by_cat()
        self.screen.fill_list()
        return [row[2] for row in self.screen.filled]

    def test_the_menu_is_tagged_with_plugin_dbs_words_at_jackds_settings_and_ordered_by_state(self):
        self.assertEqual(self.build(), [SLOW, FAST], "the refused one is not offered under the default bar")
        self.assertEqual(self.screen.engine_cats, ["Dynamics", "Delay"])
        self.screen.listbox.itemconfig.assert_not_called()
        asked = [call for call in self.commands.calls() if "lv2:urn:q:fast" in call]
        self.assertEqual(asked[0][-4:], ["--rate", "48000", "--quantum", "256"])
        self.screen.cat_index = 1
        self.screen.fill_list()
        self.assertEqual([row[2] for row in self.screen.filled], ["New Delay (PH)  unqualified · alone"])

    def test_load_all_lists_the_one_not_loaded_marked(self):
        self.assertEqual(self.build("load-all"), [SLOW, FAST, REFUSED])
        # nothing is greyed; the one that is not loaded is painted in the warning colour
        self.screen.listbox.itemconfig.assert_called_once_with(2, {'fg': "#warn"})

    def test_qualified_only_lists_the_qualified(self):
        self.assertEqual(self.build("qualified-only"), [SLOW, FAST])
        self.assertEqual(self.screen.engine_cats, ["Dynamics"], "a category with no qualified plugin is not listed")

    def test_a_plugin_that_does_not_load_is_listed_greyed(self):
        self.engines["PH/Refused"].update(NOT_WORKING="does not load", NOT_WORKING_WHY="why (LV2_ADAPTER_REFUSED)")
        self.assertEqual(self.build()[-1], "Refused Amp (PH)  not working · does not load")
        self.screen.listbox.itemconfig.assert_called_once_with(2, {'fg': "#grey"})

    def test_a_plugin_is_added_without_a_question_whatever_its_answer(self):
        self.screen.chain_manager.engine_info = self.engines
        self.screen.zyngui.modify_chain_status = {"type": "Audio Effect", "midi_thru": False}
        self.screen.bar = "load-all"
        self.screen.list_data = [("PH/Pending", 0, "", ""), ("PH/Refused", 1, "", "")]
        for n, engine in enumerate(("PH/Pending", "PH/Refused")):
            self.screen.select_action(n)
            self.screen.zyngui.show_confirm.assert_not_called()
            self.assertEqual(self.screen.zyngui.modify_chain_status["engine"], engine)
        self.assertEqual(self.screen.zyngui.modify_chain.call_count, 2)

    def test_a_jalv_row_is_not_judged_by_plugin_hostds_record(self):
        self.engines["JV/Refused"] = info("Refused Amp", "urn:q:refused", title="Refused Amp")
        self.by_cat["Dynamics"]["JV/Refused"] = self.engines["JV/Refused"]
        self.assertEqual(self.build(), [SLOW, FAST, "Refused Amp"], "the jalv row stays, plain, where the PH one is not offered")
        self.assertEqual(self.build("load-all"), [SLOW, FAST, "Refused Amp", REFUSED])

    def test_the_list_options_sort_and_filter_the_menu(self):
        self.engines["JV/Slow"] = info("Linear EQ", "urn:q:slow", title="Linear EQ")
        self.by_cat["Dynamics"]["JV/Slow"] = self.engines["JV/Slow"]
        self.build()
        self.screen.show_menu()
        title, options, cb = self.screen.zyngui.screens['option'].config.call_args.args
        self.assertEqual(title, "Plugin list")
        self.assertEqual(list(options), ["Sort by", "\u2612 State", "\u2610 Name", "\u2610 Latency", "Filter",
                                         "\u2610 plugin-hostd plugins only", "Plugins offered", "\u2610 Qualified only",
                                         "\u2612 Warn on crashes", "\u2610 Load all"])
        self.assertEqual([options[k][1] for k in list(options)[7:]], list(tiers.BARS), "the bars are plugin-db's words")
        cb("\u2610 Qualified only", options["\u2610 Qualified only"])
        self.assertEqual(self.screen.bar, "qualified-only")
        cb("\u2610 Load all", options["\u2610 Load all"])
        cb("\u2610 Latency", options["\u2610 Latency"])
        self.screen.fill_list()
        self.assertEqual([row[2] for row in self.screen.filled], [FAST, SLOW, "Linear EQ", REFUSED])
        self.screen.show_menu()
        options = self.screen.zyngui.screens['option'].config.call_args.args[1]
        self.assertIn("\u2612 Latency", options)
        cb("\u2610 plugin-hostd plugins only", options["\u2610 plugin-hostd plugins only"])
        self.screen.fill_list()
        self.assertEqual([row[2] for row in self.screen.filled], [FAST, SLOW, REFUSED])
        self.assertEqual((self.screen.list_order, self.screen.hosted_only, self.screen.index), ("latency", True, 0))

    def test_without_the_facts_of_here_the_menu_is_plain(self):
        self.screen.qualification = qual.qualification(None, self.commands.plugin_db,
                                                       os.path.join(self.commands.dir, "no-plugin-qualify"))
        with self.assertLogs(level=logging.ERROR) as logs:
            self.screen.get_engines_by_cat()
        self.assertIn("Can't ask plugin-db", logs.output[0])
        self.screen.fill_list()
        self.assertEqual([row[2] for row in self.screen.filled], ["Linear EQ (PH)", "Fast Comp (PH)", "Refused Amp (PH)"])
        self.assertEqual(self.commands.calls(), [], "nothing is asked without the facts of here")

    def test_an_unreadable_qualification_leaves_the_plain_menu(self):
        self.screen.qualification = mock.MagicMock()
        self.screen.qualification.refresh.side_effect = ValueError("broken")
        with self.assertLogs(level=logging.ERROR):
            self.screen.get_engines_by_cat()
        self.screen.fill_list()
        self.assertEqual([row[2] for row in self.screen.filled], ["Linear EQ (PH)", "Fast Comp (PH)", "Refused Amp (PH)"])

    def test_the_detail_panel_says_plugin_dbs_answer_in_its_sentences(self):
        self.engines["PH/Refused"].update(DESCR="An amp", QUALITY=0, COMPLEX=0)
        self.screen.engine_cats = []
        self.screen.show_details("PH/Refused")
        html = self.screen.zyngui.screens['help'].set_html.call_args.args[0]
        said = tiers.answer_text(plugin_db_stub.expect("refused"))
        self.assertTrue(said)
        self.assertIn(f'<div class="below_bar">{said}</div>', html)
        self.engines["JV/Refused"] = dict(self.engines["PH/Refused"])
        self.screen.show_details("JV/Refused")
        self.assertNotIn("below_bar", self.screen.zyngui.screens['help'].set_html.call_args.args[0])

    def test_the_info_panel_says_why_a_plugin_does_not_work(self):
        amp = {"NAME": "Refused Amp", "TYPE": "Audio Effect", "CAT": "Dynamics", "QUALITY": 0, "COMPLEX": 0,
               "DESCR": "An amp", "FORMAT_LINE": "LV2, run by plugin-hostd", "NOT_WORKING": "refused",
               "NOT_WORKING_WHY": "it failed qualification, so plugin-hostd does not load it (PIN_REFUSED)"}
        self.assertEqual(self.screen.description_text(amp), "An amp\n\nLV2, run by plugin-hostd\n\n"
                         "Not working: it failed qualification, so plugin-hostd does not load it (PIN_REFUSED)")
        self.assertEqual(self.screen.description_text({"DESCR": "x"}, "Below our bar: y"), "x\n\nBelow our bar: y")
        self.screen.engine_cats = []
        self.screen.get_info = lambda code=None: amp
        self.screen.show_details("PH/Refused")
        html = self.screen.zyngui.screens['help'].set_html.call_args.args[0]
        self.assertIn('<div class="not_working">Not working: it failed qualification, so plugin-hostd does not load it '
                      '(PIN_REFUSED)</div>', html)

    def test_the_info_panel_shows_the_format_line_after_the_description(self):
        surge = {"NAME": "Surge XT", "TYPE": "MIDI Synth", "CAT": "Synth", "QUALITY": 0, "COMPLEX": 0,
                 "DESCR": "Plugin by Surge Synth Team",
                 "FORMAT_LINE": "CLAP, run by plugin-hostd (an LV2 build is also installed)"}
        self.assertEqual(self.screen.description_text(surge), "Plugin by Surge Synth Team\n\n"
                         "CLAP, run by plugin-hostd (an LV2 build is also installed)")
        self.assertEqual(self.screen.description_text({"DESCR": "A jalv plugin"}), "A jalv plugin")
        self.assertEqual(self.screen.description_text({"DESCR": "", "FORMAT_LINE": "LV2, run by plugin-hostd"}),
                         "LV2, run by plugin-hostd")
        self.screen.engine_cats = []
        self.screen.get_info = lambda code=None: surge
        self.screen.show_details("PH/surge")
        html = self.screen.zyngui.screens['help'].set_html.call_args.args[0]
        self.assertIn('<div class="format">CLAP, run by plugin-hostd (an LV2 build is also installed)</div>', html)

    def test_the_enable_view_carries_a_ph_flag_to_its_jalv_entry(self):
        self.engines["JV/Linear EQ"] = info("Linear EQ", "urn:q:slow", title="Linear EQ")
        self.engines["PH/Linear EQ"] = self.engines.pop("PH/Slow")
        self.screen.show_all = True
        self.screen.list_data = [("PH/Linear EQ", 0, "", "")]
        self.screen.select_action(0)
        self.assertFalse(self.engines["PH/Linear EQ"]["ENABLED"])
        self.assertFalse(self.engines["JV/Linear EQ"]["ENABLED"])
        self.assertTrue(self.screen.engine_info_dirty)


if __name__ == "__main__":
    unittest.main()
