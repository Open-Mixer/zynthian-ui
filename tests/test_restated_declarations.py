# -*- coding: utf-8 -*-
#
# What this fork still restates of the OpenMixer libraries is listed, and the list only gets shorter
# (Open-Mixer/zynthian-ui#4): tools/restated_declarations.py agrees with tools/restated_declarations.left, a
# declaration restated again is refused, and so is a number left higher than what is there.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "tools")]

import restated_declarations as check  # noqa: E402

TOOL = os.path.join(ROOT, "tools", "restated_declarations.py")


def run(*args):
    """The hand-listed half alone: the literals have their own test (test_restated_literals.py)."""
    return subprocess.run([sys.executable, TOOL, "--no-contracts", *args], capture_output=True, text=True)


class test_restated_declarations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def tree(self):
        """A copy of the modules the check reads."""
        for path in sorted({row[1] for row in check.TABLE}):
            os.makedirs(os.path.dirname(os.path.join(self.tmp, path)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, path), os.path.join(self.tmp, path))
        return self.tmp

    def test_what_is_left_is_what_the_file_says(self):
        out = run()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_every_group_has_rows_and_every_row_a_group(self):
        self.assertEqual({row[0] for row in check.TABLE}, set(check.GROUPS))
        self.assertEqual(set(check.read_left()) - set(check.GROUPS), set())

    def test_a_declaration_restated_again_is_refused(self):
        root = self.tree()
        group, path, name = next(row[:3] for row in check.TABLE if row[2] is not None)
        before = len(check.left(root))
        with open(os.path.join(root, path), "a") as f:
            f.write("\n\ndef a_new_name():\n    pass\n")
        self.assertEqual(len(check.left(root)), before, "a name the table does not have is not a row")
        table = check.TABLE + [(group, path, "a_new_name")]
        self.assertEqual(len(check.left(root, table)), before + 1)
        wrong = check.check(check.left(root, table), check.read_left())
        self.assertEqual(len(wrong), 1, wrong)
        self.assertIn("restated again", wrong[0])
        self.assertIn(group, wrong[0])

    def test_a_verb_written_again_is_refused(self):
        root = self.tree()
        with open(os.path.join(root, check.ENGINE), "a") as f:
            f.write('\n\ndef one_more(daemon):\n    return daemon.call(f"remove {1}")\n')
        out = run("--root", root)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("verbs", out.stderr)
        self.assertIn("restated again", out.stderr)

    def test_a_replaced_row_lowers_the_number(self):
        root = self.tree()
        group, path, name = next(row[:3] for row in check.TABLE if row[2] is not None)
        with open(os.path.join(root, path)) as f:
            text = f.read()
        self.assertIn("\n%s = " % name, text)
        with open(os.path.join(root, path), "w") as f:
            f.write(text.replace("\n%s = " % name, "\n_gone = ", 1))
        out = run("--root", root)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s: " % group, out.stderr)
        self.assertIn("lower the number", out.stderr)

    def test_none_is_refused_while_a_row_is_left(self):
        if not check.left():
            self.skipTest("nothing is left")
        out = run("--none")
        self.assertEqual(out.returncode, 1)
        self.assertIn("are left", out.stderr)

    def test_none_passes_a_tree_with_nothing_left(self):
        os.makedirs(os.path.join(self.tmp, "zyngine"))
        out = run("--root", self.tmp, "--none")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("none left", out.stdout)

    def test_a_group_the_check_does_not_have_is_refused(self):
        left = os.path.join(self.tmp, "left")
        shutil.copy(check.LEFT, left)
        with open(left, "a") as f:
            f.write("nothing 3\n")
        out = run("--left", left)
        self.assertEqual(out.returncode, 1)
        self.assertIn("nothing is not a group", out.stderr)


if __name__ == "__main__":
    unittest.main()
