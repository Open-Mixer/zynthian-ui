# -*- coding: utf-8 -*-
#
# What the plugin-hostd tests stand on in this suite's harness (tests/conftest.py, tests/bootstrap.py).
#
# need(): the packages the plugin-hostd engine needs are not Zynthian's (plugin-hostd's Python client, omx-contract's
# readers, plugin-db's reader). Zynthian imports and runs without them, the engine then saying it is unavailable; a
# test module that exercises the engine calls need() first and is skipped, naming what is missing, when they are not
# installed. With them installed it runs whole.
#
# stand_in(): the conftest imports the real zyngine, zynautoconnect and zynthian_lv2 before any test file, so the
# engine tests put their doubles ON those modules for the length of each test: AUTOCONNECT stands in for zynautoconnect
# (in sys.modules and in every loaded module that imported the real one), and zynthian_lv2 answers the ports and
# presets of LV2_PORTS and LV2_PRESETS. This module is imported by its package name only, so every test file shares
# one AUTOCONNECT and one LV2_PORTS, however the test file that imports it was itself imported.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib
import sys
from unittest import mock

import pytest

# module => what installs it
PACKAGES = {
    "plugin_hostd_protocol": "plugin-hostd's Python client (python3-plugin-hostd-protocol)",
    "omx_contract_catalog": "omx-contract's catalog reader (omx-contract-data)",
    "omx_contract_scale": "omx-contract's position law (omx-contract-data)",
    "plugin_db": "plugin-db's reader (python3-plugin-db)",
}
ENGINE = ("plugin_hostd_protocol", "omx_contract_catalog", "omx_contract_scale")


def missing(*modules):
    """The modules of `modules` (all of PACKAGES when none is named) that do not import here, each with what installs it."""
    importlib.import_module("zyngine.zynthian_position_law")  # puts omx-contract's directory on sys.path
    absent = []
    for name in modules or tuple(PACKAGES):
        try:
            importlib.import_module(name)
        except ImportError:
            absent.append(f"{name}, {PACKAGES[name]}")
    return absent


def need(*modules):
    """Skip the calling test module unless every named module imports (the engine's when none is named)."""
    absent = missing(*(modules or ENGINE))
    if absent:
        pytest.skip("not installed: " + "; ".join(absent), allow_module_level=True)


AUTOCONNECT = mock.MagicMock(name="zynautoconnect")
REAL_AUTOCONNECT = importlib.import_module("zynautoconnect")
LV2 = importlib.import_module("zyngine.zynthian_lv2")
# zynthian_lv2's ports of the test plugins, by URI; a test file adds its own
LV2_PORTS = {"urn:test:amp": {0: {"symbol": "gain", "name": "Gain", "range": {"min": -90, "max": 90}, "value": 0,
                                  "is_integer": False, "is_toggled": False}}}
# the presets Zynthian's cache holds for an LV2 plugin, by plugin name, as jalv reads them: a bank label to its URL and
# presets; a test sets it, and a plugin it does not name has none
LV2_PRESETS = {}


def _replace(case, owner, name, value):
    """owner.name (a module attribute, or a key when owner is a dict) is value until the test ends."""
    if isinstance(owner, dict):
        had, old = name in owner, owner.get(name)
        owner[name] = value
        case.addCleanup(lambda: owner.__setitem__(name, old) if had else owner.pop(name, None))
    else:
        patcher = mock.patch.object(owner, name, value)
        patcher.start()
        case.addCleanup(patcher.stop)


def stand_in(case):
    """The doubles of one test (a unittest.TestCase): AUTOCONNECT for zynautoconnect, and zynthian_lv2's lists by type
    empty, its ports and presets those of LV2_PORTS and LV2_PRESETS."""
    for module in [m for m in list(sys.modules.values()) if getattr(m, "zynautoconnect", None) is REAL_AUTOCONNECT]:
        _replace(case, module, "zynautoconnect", AUTOCONNECT)
    _replace(case, sys.modules, "zynautoconnect", AUTOCONNECT)
    _replace(case, LV2, "engines_by_type", {"MIDI Synth": {}, "Audio Effect": {}})
    _replace(case, LV2, "get_plugin_ports", lambda uri: LV2_PORTS.get(uri, {}))
    _replace(case, LV2, "get_plugin_presets_cache", lambda name: LV2_PRESETS.get(name, {}))


def sabotage_tree(tmp, copied=("zyngine", "tests")):
    """A tree in tmp that runs this suite as this one does and that a sabotage arm may break: the copied directories
    are copies, every other entry of this tree is linked (the harness imports zynautoconnect, zyngui, zynconf...)."""
    import os
    import shutil
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in os.listdir(root):
        if name in (".git", "venv") or name.startswith(".pytest") or name.startswith(".ruff"):
            continue
        if name in copied:
            shutil.copytree(os.path.join(root, name), os.path.join(tmp, name),
                            ignore=shutil.ignore_patterns("__pycache__", "build"))
        else:
            os.symlink(os.path.join(root, name), os.path.join(tmp, name))
    return tmp
