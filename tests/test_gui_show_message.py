# -*- coding: utf-8 -*-
#
# R60 (#98), the last hunk of the Pi's "zui-pass local patch before the fork head": a message sent while the current
# screen's set_title takes no timeout (the loading screen at start-up, when a snapshot restore says what it could not
# load) is still shown, with the message alone, and anything else that fails is logged, not raised. The rest of the
# patch (the unbuilt processors kept in the snapshot, the daemon answering before the add) is held by
# test_ph_chain_survives_restart.
#
# zynthian_gui imports the whole UI (Tk, zyncoder, the JACK libraries), so the method is read out of the module's own
# source and run as it is written there.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import logging
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUI = os.path.join(os.path.dirname(HERE), "zyngui", "zynthian_gui.py")


def cb_show_message():
    """zynthian_gui.cb_show_message as the module defines it."""
    with open(GUI, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "zynthian_gui")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "cb_show_message")
    namespace = {"logging": logging}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), GUI, "exec"), namespace)
    return namespace["cb_show_message"]


class Screen:
    def __init__(self):
        self.titles = []


class TimedScreen(Screen):
    def set_title(self, title, fg=None, bg=None, timeout=None):
        self.titles.append((title, timeout))


class LoadingScreen(Screen):
    def set_title(self, title):  # the loading screen's: no colours, no timeout
        self.titles.append((title, None))


class BrokenScreen(Screen):
    def set_title(self, *args):
        raise RuntimeError("no title bar")


class Gui:
    def __init__(self, screen):
        self.screen = screen

    def get_current_screen_obj(self):
        return self.screen


class ShowMessage(unittest.TestCase):

    def test_a_screen_with_a_timeout_shows_the_message_for_it(self):
        gui = Gui(TimedScreen())
        cb_show_message()(gui, "Not loaded: x", timeout=8)
        self.assertEqual(gui.screen.titles, [("Not loaded: x", 8)])

    def test_the_loading_screen_shows_the_message_without_a_timeout(self):
        gui = Gui(LoadingScreen())
        cb_show_message()(gui, "Not loaded: x", timeout=8)
        self.assertEqual(gui.screen.titles, [("Not loaded: x", None)])

    def test_a_screen_that_fails_is_logged_not_raised(self):
        gui = Gui(BrokenScreen())
        with self.assertLogs(level="ERROR") as logs:
            cb_show_message()(gui, "Not loaded: x", timeout=8)
        self.assertIn("Can't show GUI message", logs.output[0])


if __name__ == "__main__":
    unittest.main()
