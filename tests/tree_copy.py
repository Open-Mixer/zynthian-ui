# -*- coding: utf-8 -*-
#
# A copy of this tree that the suite runs in, for the sabotage tests (test_panel_gestures_sabotage,
# test_pages_conformance): they break one module in the copy and run a few test files there. The copy holds what
# tests/conftest.py imports (zyngine, zynautoconnect, zynconf, zyngui and zynlibs' bindings) and pyproject.toml, which
# carries the suite's options; without them pytest refuses to start in the copy (exit 4).
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = ("zyngine", "zyngui", "zynautoconnect", "zynconf", "zynlibs", "tests")
FILES = ("pyproject.toml", "zynthian_state_schema.py")


def copy_core(dest):
    """Copy the Python core, the tests and the pytest configuration into the directory `dest`."""
    for d in PACKAGES:
        shutil.copytree(os.path.join(ROOT, d), os.path.join(dest, d), ignore=shutil.ignore_patterns("__pycache__", "build"))
    for f in FILES:
        shutil.copy(os.path.join(ROOT, f), dest)
