#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Engine (zynthian_ui_look)
#
# The UI's look as omx-panel's renderer takes it (docs/ui-look-drawn-widgets.md): the renderer draws from colour roles
# (omx-panel schema/look-roles.json) and refuses a look short of any, so the host values every role. The base is the
# renderer's own look.json, the file it reads by default from its tools directory (every role at its default, the
# console's dark theme); over it, the roles Zynthian's palette has a colour for take zynthian_gui_config's colour, the
# one the level-1 preset (zynthian-sys config/ui-looks) generated from the same console token. Nothing here types a
# colour or a role name the renderer's file does not carry.
#
# Standard library only: the renderer's process imports this module too.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import json
import os

# The palette table: a colour role of the renderer, and the zynthian_gui_config colour that values it (the same console
# token under the vintage preset: --surface, --surface-3, --meter-track, --ink, --ink-dim, --legend, --accent,
# --state-engaged, --meter-green, --meter-amber, --danger)
ROLES = (("--surface", "color_panel_bg"), ("--surface-3", "color_panel_hl"), ("--glass", "color_off"),
         ("--ink", "color_tx"), ("--ink-dim", "color_tx_off"), ("--legend", "color_hl"), ("--accent", "color_on"),
         ("--state-engaged", "color_ml"), ("--meter-green", "color_midi"), ("--meter-amber", "color_alt2"),
         ("--meter-red", "color_error"))

STOCK = "stock"


class LookShort(Exception):
    """The renderer's look is not one this table can value (no tokens, or no role the table names): said by name; the
    caller draws stock and says it once."""


_cache = {}  # (ui_look, tools_dir) -> the look document, or the LookShort it raised: the base is read once


def tokens(colors, base):
    """The look document for the renderer: <base> (its look.json, parsed) with the palette's roles valued from
    <colors> (zynthian_gui_config, or anything with its color_* attributes). LookShort names what the base lacks."""
    if not isinstance(base, dict) or not isinstance(base.get("tokens"), dict):
        raise LookShort("the renderer's look has no tokens: not a look.json")
    tok = dict(base["tokens"])
    for role, name in ROLES:
        if role not in tok:
            raise LookShort(f"the renderer's look names no role {role} (for {name}): its look.json and this table disagree")
        tok[role] = getattr(colors, name)
    return {**base, "tokens": tok}


def _mix(a, b, t):
    """The colour a fraction t of the way from the hex colour a to b."""
    ca, cb = [tuple(int(c[k:k + 2], 16) for k in (1, 3, 5)) for c in (a, b)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def cpu_colour(colors, cpu_load):
    """The status icon's colour under a look: the look's meter green below 50 % CPU load, green to amber up to 75 %, amber
    to red up to 100 %, each stop the colour <colors> holds for the --meter-green, --meter-amber and --meter-red roles
    (the table above). None under stock, whose gradient is upstream's (zynthian_gui_base.refresh_status)."""
    if getattr(colors, "ui_look", STOCK) == STOCK:
        return None
    by_role = dict(ROLES)
    green, amber, red = (getattr(colors, by_role[r]) for r in ("--meter-green", "--meter-amber", "--meter-red"))
    load = min(max(cpu_load, 0), 100)
    if load <= 50:
        return green
    if load <= 75:
        return _mix(green, amber, (load - 50) / 25)
    return _mix(amber, red, (load - 75) / 25)


def look_for(config, tools_dir):
    """The look a view is opened with under <config>'s ui_look: None under stock (the renderer's own look), else the
    palette over the renderer's look.json in <tools_dir>; None too when that file is not there (the renderer is
    absent, and says so itself when the view is opened)."""
    look = getattr(config, "ui_look", STOCK)
    if look == STOCK:
        return None
    key = (look, tools_dir)
    if key not in _cache:
        try:
            with open(os.path.join(tools_dir, "look.json")) as f:
                base = json.load(f)
        except (OSError, ValueError):
            return None
        try:
            _cache[key] = tokens(config, base)
        except LookShort as e:
            _cache[key] = e
    if isinstance(_cache[key], LookShort):
        raise _cache[key]
    return _cache[key]
