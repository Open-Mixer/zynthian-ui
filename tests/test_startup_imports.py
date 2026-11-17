# -*- coding: utf-8 -*-
#
# The engine screen imports the way zynthian_main.py does, with the real zyngine package: a name that
# the package exports for a class and a module alike must resolve to the module where a function is used.
# Needs a Zynthian: tkinter and PIL.ImageTk, the zyncoder and zynlibs native libraries on JACK, and the tree under
# /zynthian (config, wiring profiles) that zynthian_gui_config reads at import. The CI container is Debian with
# python3 and pytest and none of that (the zyncoder directory of this repository is a submodule that is not checked
# out there), so it cannot run in CI: it skips with the reason, and runs on the Pi with `python3 -m pytest
# tests/test_startup_imports.py`.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import ast
import sys
import glob
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class startup_imports(unittest.TestCase):

    def test_the_engine_screen_resolves_the_estimate_function_and_the_chain_options_the_daemon(self):
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        try:
            from zyngui import zynthian_gui_engine, zynthian_gui_chain_options
        except (ImportError, OSError) as e:  # no tkinter or zyncoder, or no /zynthian tree to read
            self.skipTest(f"not a Zynthian, so it cannot run in CI (it needs the Zynthian's tkinter, zyncoder and /zynthian tree) and runs on the Pi: {e}")
        for screen in (zynthian_gui_engine, zynthian_gui_chain_options):
            self.assertTrue(hasattr(screen.plugin_hostd, "estimate"), screen.__name__)
            self.assertTrue(hasattr(screen.plugin_hostd, "daemon"), screen.__name__)
        self.assertTrue(callable(zynthian_gui_engine.plugin_hostd.estimate))
        self.assertTrue(callable(zynthian_gui_engine.plugin_hostd.audio_format))
        self.assertTrue(callable(zynthian_gui_engine.plugin_hostd.menu_refs))

    def test_no_screen_reaches_a_module_function_through_a_name_that_is_a_class(self):
        """zyngine/__init__ star-imports each engine, so `from zyngine import zynthian_engine_x` yields the
        class where the module has a class of that name: `name.function` for a function of the module is an
        AttributeError at startup. Source level, so it holds where tkinter and the native libraries are absent."""
        shadowed = []
        for path in sorted(glob.glob(os.path.join(ROOT, "zyngui", "*.py"))):
            tree = ast.parse(open(path).read())
            for node in ast.walk(tree):
                if not (isinstance(node, ast.ImportFrom) and node.module == "zyngine"):
                    continue
                for alias in node.names:
                    module = os.path.join(ROOT, "zyngine", alias.name + ".py")
                    if not os.path.exists(module):
                        continue
                    body = ast.parse(open(module).read()).body
                    if not any(isinstance(n, ast.ClassDef) and n.name == alias.name for n in body):
                        continue
                    functions = {n.name for n in body if isinstance(n, ast.FunctionDef)}
                    for use in ast.walk(tree):
                        if (isinstance(use, ast.Attribute) and isinstance(use.value, ast.Name)
                                and use.value.id == (alias.asname or alias.name) and use.attr in functions):
                            shadowed.append(f"{os.path.basename(path)}: {use.value.id}.{use.attr}")
        self.assertEqual(shadowed, [])

if __name__ == "__main__":
    unittest.main()
