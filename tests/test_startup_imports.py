# -*- coding: utf-8 -*-
#
# The engine screen imports the way zynthian_main.py does, with the real zyngine package: a name that
# the package exports for a class and a module alike must resolve to the module where a function is used.
# Needs a Zynthian: tkinter and PIL.ImageTk, the zyncoder and zynlibs native libraries on JACK, and the tree under
# /zynthian (config, wiring profiles) that zynthian_gui_config reads at import. The CI container is Debian with
# python3 and pytest and none of that (the zyncoder directory of this repository is a submodule that is not checked
# out there), so it cannot run in CI. The skip is decided from the host, before the import: no /zynthian tree, no
# attempt, a skip that says so. On a host that has the tree (the Pi: `python3 -m pytest tests/test_startup_imports.py`)
# nothing is caught, so any import error, of a dependency, of our own module or of a library, fails.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import ast
import sys
import glob
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZYNTHIAN_TREE = "/zynthian"  # what zynthian_gui_config reads at import; a host without it is not a Zynthian


class startup_imports(unittest.TestCase):

    def run_with_import_raising(self, error, tree=True):
        """The engine-screen test, with the zyngui import raising `error`, on a host that has the /zynthian tree
        (tree=True: a directory that exists) or has none (a path that does not): how it ends."""
        fake = types.ModuleType("zyngui")
        fake.__path__ = []

        def fail(name):
            raise error
        fake.__getattr__ = fail
        outcome = unittest.TestResult()
        here = ROOT if tree else os.path.join(ROOT, "no-such-zynthian-tree")
        with mock.patch.dict(sys.modules, {"zyngui": fake}), mock.patch.object(sys.modules[__name__], "ZYNTHIAN_TREE", here):
            startup_imports("test_the_engine_screen_resolves_the_estimate_function_and_the_chain_options_the_daemon").run(outcome)
        return outcome

    def assertFails(self, error):
        outcome = self.run_with_import_raising(error)
        self.assertEqual((len(outcome.skipped), len(outcome.errors)), (0, 1), f"on a host with the tree, {error!r} is a red, never a skip")

    def test_a_native_library_that_fails_to_load_fails_the_test(self):
        self.assertFails(OSError("cannot load libzyncore.so"))

    def test_an_extension_that_is_there_and_fails_to_load_fails_the_test(self):
        self.assertFails(ImportError("libzyncore.so: undefined symbol: foo"))

    def test_a_missing_dependency_fails_the_test(self):
        self.assertFails(ModuleNotFoundError("No module named 'psutil'"))

    def test_a_module_of_ours_that_is_missing_fails_the_test(self):
        self.assertFails(ModuleNotFoundError("No module named 'zyngine.zynthian_lv2'"))

    def test_a_file_that_is_missing_somewhere_else_fails_the_test(self):
        self.assertFails(FileNotFoundError("/usr/share/somewhere/else.json"))

    def test_an_unreadable_file_fails_the_test(self):
        self.assertFails(PermissionError("/zynthian/config"))

    def test_a_host_with_no_zynthian_tree_skips_without_importing(self):
        outcome = self.run_with_import_raising(AssertionError("the import was attempted"), tree=False)
        self.assertEqual((len(outcome.skipped), len(outcome.errors)), (1, 0))

    def test_the_engine_screen_resolves_the_estimate_function_and_the_chain_options_the_daemon(self):
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        if not os.path.isdir(ZYNTHIAN_TREE):
            self.skipTest(f"not a Zynthian: there is no {ZYNTHIAN_TREE} tree, so the UI cannot be imported here (CI is one such "
                          "host); it runs on the Pi, where any import error fails")
        from zyngui import zynthian_gui_engine, zynthian_gui_chain_options
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
