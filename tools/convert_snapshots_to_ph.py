#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: convert_snapshots_to_ph
#
# Run once by hand: rewrites the jalv (JV) processors of saved snapshots into plugin-hostd (PH)
# processors of the same plugin, with the same controller values and preset. Each result is written
# beside its snapshot, foo.zss as foo.ph.zss, and nothing is ever overwritten. Zynthian itself never
# converts a snapshot when it loads one. Every instrument and effect is converted, whatever plugin-db
# answers for it: the ones it answers refused or absent for are reported with its sentences. None is
# left on jalv.
#
#   convert_snapshots_to_ph.py [--engine-config FILE] [--store DIR] [--suffix .ph] SNAPSHOT_OR_DIR...
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import os
import sys
import json
import types
import argparse
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_VERSION = 5  # zynthian_legacy_snapshot.SNAPSHOT_SCHEMA_VERSION
# the banks zynthian_engine_plugin_hostd lists: Factory, and User for the presets Zynthian saved under jalv
FACTORY_BANK = ["factory", None, "Factory", None]
USER_BANK = ["user", None, "User", None]


def bare_package():
    """The zyngine package without running its __init__, which imports every engine and its libraries: the modules
    loaded here import each other as zyngine.<module>. A zyngine already imported (the UI's, or a test's) is kept."""
    if "zyngine" not in sys.modules:
        package = types.ModuleType("zyngine")
        package.__path__ = [os.path.join(ROOT, "zyngine")]
        sys.modules["zyngine"] = package


def load_module(name):
    """A zyngine module by its path: the zyngine package imports every engine and its libraries."""
    bare_package()
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "zyngine", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


catalogue = load_module("zynthian_plugin_hostd_catalogue")
qualification = load_module("zynthian_plugin_qualification")
tiers = load_module("zynthian_plugin_tiers")


def default_engine_config():
    return os.path.join(os.environ.get("ZYNTHIAN_CONFIG_DIR") or "/zynthian/config", "engine_config.json")


def why_not(eng_code, engines):
    """None when plugin-hostd hosts the processor's plugin, else the reason it stays."""
    if not eng_code.startswith("JV/"):
        return f"{eng_code} is not a jalv plugin"
    info = engines.get(eng_code)
    if not info or not info.get("URL"):
        return f"{eng_code} is not in the engine config, so its plugin URL is unknown"
    if info.get("TYPE") not in catalogue.ENGINE_TYPES:
        return f"{eng_code} is a {info.get('TYPE')}: plugin-hostd hosts instruments and effects"
    return None


def ph_processor_state(state):
    """A jalv processor's zs3 state for the PH engine: controllers as they are, the preset by its URL, in the bank
    the engine lists it in: User for a preset saved under jalv (a file in presets/lv2), Factory for the others."""
    state = dict(state)
    preset = state.get("preset_info")
    url = preset[0] if preset and isinstance(preset[0], str) else ""
    bank = USER_BANK if url.startswith("file://") and "/presets/lv2/" in url else FACTORY_BANK
    if url:
        state["preset_info"] = [url, None, preset[2] if len(preset) > 2 else url, bank[0]]
    else:
        state["preset_info"] = None
    state["bank_info"] = list(bank)
    state["bank_subdir_info"] = None
    state["preset_subdir_info"] = None
    return state


def not_loaded_text(answer):
    """plugin-db's sentences for a plugin it does not load as things stand (refused, absent); None for the rest."""
    if not answer or answer["state"] not in (tiers.v.states.refused, tiers.v.states.absent):
        return None
    return tiers.answer_text(answer)


def convert_state(snapshot, engines, answer_of=None):
    """(converted snapshot, report rows). A row is (processor id, engine code, new code or None, reason, what
    plugin-db says of a plugin it does not load, or None). answer_of(url): plugin-db's answer for it."""
    rows = []
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        return None, [(None, None, None, f"schema {snapshot.get('schema_version')} is not {SCHEMA_VERSION}: "
                                         "load and save it once in Zynthian, then convert", None)]
    snapshot = json.loads(json.dumps(snapshot))
    moved = {}
    for chain_id, chain in snapshot.get("chains", {}).items():
        for slot in chain.get("slots", []):
            for proc_id, eng_code in slot.items():
                reason = why_not(eng_code, engines)
                if reason:
                    rows.append((proc_id, eng_code, None, reason, None))
                    continue
                slot[proc_id] = moved[proc_id] = "PH/" + eng_code[3:]
                url = engines[eng_code]["URL"]
                rows.append((proc_id, eng_code, slot[proc_id], url, not_loaded_text(answer_of(url)) if answer_of else None))
    for zs3 in snapshot.get("zs3", {}).values():
        processors = zs3.get("processors", {})
        for proc_id in moved:
            if proc_id in processors:
                processors[proc_id] = ph_processor_state(processors[proc_id])
    return (snapshot if moved else None), rows


def target_path(path, suffix):
    base, ext = os.path.splitext(path)
    return f"{base}{suffix}{ext}"


def snapshot_files(paths, suffix):
    for path in paths:
        if os.path.isdir(path):
            for top, dirs, files in os.walk(path):
                dirs.sort()
                for name in sorted(files):
                    if name.endswith(".zss") and not name.endswith(suffix + ".zss"):
                        yield os.path.join(top, name)
        else:
            yield path


def convert_file(path, engines, suffix, out, answer_of=None):
    """Convert one snapshot. Returns (converted, left, written, below): below, the converted ones plugin-db does
    not load."""
    target = target_path(path, suffix)
    try:
        with open(path) as f:
            snapshot = json.load(f)
    except (OSError, ValueError) as e:
        print(f"{path}: not read ({e})", file=out)
        return 0, 0, False, 0
    converted, rows = convert_state(snapshot, engines, answer_of)
    if converted is None:
        print(f"{path}: left as it is", file=out)
    elif os.path.exists(target):
        print(f"{path}: {target} exists, left as it is (nothing is overwritten)", file=out)
        converted = None
    else:
        print(f"{path} -> {target}", file=out)
    for proc_id, eng_code, new_code, reason, below in rows:
        if proc_id is None:
            print(f"  left       {reason}", file=out)
        elif new_code and converted is not None:
            print(f"  converted  processor {proc_id} {eng_code} -> {new_code} ({reason})", file=out)
            if below:
                print(f"  not loaded processor {proc_id} {new_code}: {below}", file=out)
        elif new_code:
            print(f"  left       processor {proc_id} {eng_code}: would become {new_code}", file=out)
        else:
            print(f"  left       processor {proc_id}: {reason}", file=out)
    n_converted = sum(1 for r in rows if r[2]) if converted is not None else 0
    n_left = sum(1 for r in rows if r[0] is not None) - n_converted
    if converted is None:
        return n_converted, n_left, False, 0
    try:
        # "x" mode: a file that appeared since the check is not overwritten either
        with open(target, "x") as f:
            json.dump(converted, f)
    except OSError as e:
        print(f"  not written: {e}", file=out)
        return 0, n_left + n_converted, False, 0
    return n_converted, n_left, True, sum(1 for r in rows if r[2] and r[4])


def main(argv=None, out=sys.stdout):
    parser = argparse.ArgumentParser(description="Write a plugin-hostd copy of each snapshot that holds jalv plugins.")
    parser.add_argument("paths", nargs="+", help="snapshot files or directories of them")
    parser.add_argument("--engine-config", default=default_engine_config(),
                        help="Zynthian's engine config, for each jalv plugin's URL and type (default: %(default)s)")
    parser.add_argument("--store", default=None,
                        help="plugin-db's store, for what it answers for each plugin (default: plugin-db's own)")
    parser.add_argument("--suffix", default=".ph", help="added before .zss in the name of each result (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        with open(args.engine_config) as f:
            engines = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Can't read the engine config {args.engine_config}: {e}", file=out)
        return 2
    q = qualification.qualification(args.store)

    def answer_of(url):
        try:
            return q.answer(url)
        except qualification.HereError as e:
            if not answer_of.said:
                print(f"plugin-db is not asked: {e}", file=out)
                answer_of.said = True
            return None
    answer_of.said = False
    totals = [0, 0, 0, 0, 0]
    for path in snapshot_files(args.paths, args.suffix):
        converted, left, written, below = convert_file(path, engines, args.suffix, out, answer_of)
        totals = [totals[0] + 1, totals[1] + written, totals[2] + converted, totals[3] + left, totals[4] + below]
    print(f"{totals[0]} snapshots read, {totals[1]} written; {totals[2]} processors converted, {totals[3]} left as they are; "
          f"{totals[4]} converted processor{'' if totals[4] == 1 else 's'} not loaded (listed above)", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
