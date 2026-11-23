# -*- coding: utf-8 -*-
#
# tests/upstream-suites.txt is what upstream's tests workflow runs in this fork: exactly the subdirectories of tests/
# that hold tests, so a suite upstream adds is run there the day it arrives, and none is left out by hand.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def listed():
    with open(os.path.join(HERE, "upstream-suites.txt")) as f:
        return sorted(line.strip() for line in f if line.strip() and not line.startswith("#"))


def suites():
    found = []
    for name in sorted(os.listdir(HERE)):
        path = os.path.join(HERE, name)
        if os.path.isdir(path) and any(f.startswith("test_") and f.endswith(".py")
                                       for _, _, files in os.walk(path) for f in files):
            found.append(f"tests/{name}")
    return found


class UpstreamSuites(unittest.TestCase):
    def test_the_list_is_every_subdirectory_that_holds_tests(self):
        self.assertEqual(listed(), suites())

