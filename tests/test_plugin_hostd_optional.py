# -*- coding: utf-8 -*-
#
# The plugin-hostd engine's packages are optional: Zynthian imports and runs without plugin-hostd's Python client,
# omx-contract's readers and plugin-db's reader. Each check runs in a fresh interpreter (this suite's bootstrap first)
# where those modules cannot be imported, whether this machine has them or not: the core imports, the engine says it
# is unavailable and why, its menu entries are marked not working with the reason, and the menus still list plugins.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCKED = ("plugin_hostd_protocol", "plugin_hostd_client", "omx_contract_catalog", "omx_contract_scale", "plugin_db")

# a finder that refuses the blocked modules, as on a machine that never installed them
PRELUDE = f"""
import sys
sys.path.insert(0, {REPO!r})
BLOCKED = {BLOCKED!r}


class Absent:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {{name!r}}", name=name)
        return None


sys.meta_path.insert(0, Absent())
import tests.bootstrap  # noqa
import json
"""


def run(code):
    """What the code prints as JSON, run after PRELUDE in a fresh interpreter."""
    proc = subprocess.run([sys.executable, "-c", PRELUDE + code], cwd=REPO, env=dict(os.environ, PYTHONWARNINGS="ignore"),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_zynthian_imports_without_them():
    out = run("""
import zyngine.zynthian_state_manager  # the import order this suite's conftest uses
import zyngine, zyngine.zynthian_chain_manager, zynautoconnect
print(json.dumps([m for m in BLOCKED if m in sys.modules]))
""")
    assert out == [], "nothing blocked was imported"


def test_the_engine_says_it_is_unavailable_and_why():
    out = run("""
import importlib
ph = importlib.import_module("zyngine.zynthian_engine_plugin_hostd")
from zyngine import zynthian_position_law as law, zynthian_plugin_hostd_protocol as p
from zyngine import zynthian_plugin_qualification as q, zynthian_plugin_tiers as tiers
print(json.dumps({"loaded": ph.protocol.loaded, "failure": ph.protocol.failure, "protocol": p.MISSING,
                  "law": law.MISSING, "qualification": q.MISSING, "tiers": tiers.MISSING, "bar": tiers.plugin_bar(),
                  "bars": list(tiers.BARS)}))
""")
    assert out["loaded"] is False
    assert "is not installed" in out["failure"]
    for key in ("protocol", "law", "qualification", "tiers"):
        assert "is not installed" in out[key], key
    assert out["bar"] is None and out["bars"] == [], "no bar to choose without plugin-db"


def test_a_controller_without_a_law_is_untouched_and_a_law_asked_for_says_why():
    out = run("""
from zyngine import zynthian_position_law as law
from zyngine.zynthian_controller import zynthian_controller
z = zynthian_controller(None, "level", {"value_min": 0, "value_max": 100, "value": 50, "is_integer": False})
z.nudge(1)
try:
    law.scale_position({"scale": "log", "min": 20, "max": 20000}, 1000)
    said = None
except law.LawAbsent as e:
    said = str(e)
print(json.dumps({"value": z.value, "law": z.position_law, "said": said}))
""")
    assert out["law"] is None
    assert out["value"] != 50, "the controller still moves"
    assert "omx_contract_scale is not installed" in out["said"]


def test_the_menus_list_plugins_and_mark_the_engines_as_not_working():
    out = run("""
from zyngine import zynthian_plugin_hostd_catalogue as cat, zynthian_plugin_tiers as tiers
engines = {"JV/Amp": {"ID": "Amp", "NAME": "Amp", "TITLE": "Amp", "TYPE": "Audio Effect", "CAT": "Other",
                      "ENABLED": True, "URL": "urn:test:amp"}}
cat.add_catalogue(engines, clap=[], binary=sys.executable)
rows = tiers.menu_entries(engines, lambda url: None, tiers.plugin_bar())
print(json.dumps({"ph": engines["PH/Amp"], "rows": rows}))
""")
    assert out["ph"]["NOT_WORKING"] == "not installed"
    assert "plugin_hostd_protocol" in out["ph"]["NOT_WORKING_WHY"] or "omx_contract" in out["ph"]["NOT_WORKING_WHY"]
    assert [key for key, _, _ in out["rows"]] == ["JV/Amp", "PH/Amp"], "the jalv row first, the greyed one after it"
    assert out["rows"][1][2] is True, "greyed"
