# -*- coding: utf-8 -*-
#
# The update check asks zynthian-sys which release tag the updater would take
# (scripts/omx-release-target.sh), so it reports an update only when
# update_zynthian.sh would move the device. Without that script it keeps the
# stock rule. Runs with plain `python3 -m unittest`.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import re
import sys
import types
import tempfile
import unittest
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT]

if "zyngine" not in sys.modules:
    _pkg = types.ModuleType("zyngine")
    _pkg.__path__ = [os.path.join(ROOT, "zyngine")]
    sys.modules["zyngine"] = _pkg
from zyngine import zynthian_release_target as rt  # noqa: E402

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")


class release_target_case(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = os.path.join(tmp.name, "zynthian-ui")
        self.sys_dir = os.path.join(tmp.name, "zynthian-sys")
        self.calls = os.path.join(tmp.name, "calls")
        os.makedirs(os.path.join(self.sys_dir, "scripts"))
        self.git("init", "-q", "-b", "vangelis-2610-omx.2", self.repo, cwd=tmp.name)
        with open(os.path.join(self.repo, "f"), "w") as f:
            f.write("1\n")
        self.git("add", "f")
        self.git("commit", "-q", "-m", "one", "--", "f")
        # what a device has after an update: our tags, and upstream's newer one
        for tag in ("vangelis-2610", "vangelis-2610-omx.1", "vangelis-2610-omx.2", "vangelis-2610.1"):
            self.git("tag", tag)

    def git(self, *args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd or self.repo, env=GIT_ENV, check=True)

    def script(self, body):
        path = os.path.join(self.sys_dir, "scripts", "omx-release-target.sh")
        with open(path, "w") as f:
            f.write(f"#!/bin/sh\necho \"$@\" >> {self.calls}\n{body}\n")
        os.chmod(path, 0o755)

    def test_the_target_is_the_tag_the_sys_script_names(self):
        self.script("echo vangelis-2610-omx.2")
        self.assertEqual(rt.release_target(self.repo, "vangelis", self.sys_dir), "vangelis-2610-omx.2")
        with open(self.calls) as f:
            self.assertEqual(f.read(), f"--fetch {self.repo} vangelis\n")

    def test_on_the_target_tag_there_is_no_update_though_an_upstream_tag_sorts_after_it(self):
        self.script("echo 'zynthian-ui: vangelis-2610.1 does not contain the tip' >&2; echo vangelis-2610-omx.2")
        self.assertFalse(rt.update_available(self.repo, "vangelis", self.sys_dir))

    def test_a_newer_target_is_an_update(self):
        self.script("echo vangelis-2610-omx.3")
        self.assertTrue(rt.update_available(self.repo, "vangelis", self.sys_dir))

    def test_no_tag_to_take_is_no_update(self):
        self.script("echo 'zynthian-ui: no release tag to take' >&2; exit 1")
        self.assertIsNone(rt.release_target(self.repo, "vangelis", self.sys_dir))
        self.assertFalse(rt.update_available(self.repo, "vangelis", self.sys_dir))

    def test_without_the_sys_script_the_stock_rule_stands(self):
        self.assertEqual(rt.release_target(self.repo, "vangelis", self.sys_dir), "vangelis-2610.1")
        self.assertTrue(rt.update_available(self.repo, "vangelis", self.sys_dir))

    def test_the_sys_directory_comes_from_the_environment(self):
        self.script("echo vangelis-2610-omx.2")
        old = os.environ.get("ZYNTHIAN_SYS_DIR")
        os.environ["ZYNTHIAN_SYS_DIR"] = self.sys_dir
        try:
            self.assertEqual(rt.release_target(self.repo, "vangelis"), "vangelis-2610-omx.2")
        finally:
            if old is None:
                del os.environ["ZYNTHIAN_SYS_DIR"]
            else:
                os.environ["ZYNTHIAN_SYS_DIR"] = old


class state_manager_case(unittest.TestCase):
    """The state manager is not importable off a device: its source is read."""

    def setUp(self):
        with open(os.path.join(ROOT, "zyngine", "zynthian_state_manager.py")) as f:
            src = f.read()
        self.body = re.search(r"    def check_for_updates\(self\):\n(.*?)\n    # -{20,}", src, re.S).group(1)

    def test_the_update_check_asks_the_release_target(self):
        self.assertIn("zynthian_release_target.update_available(path, stable_branch)", self.body)

    def test_the_update_check_no_longer_takes_the_last_tag_listed(self):
        self.assertNotIn("stags[-1]", self.body)


if __name__ == "__main__":
    unittest.main()
