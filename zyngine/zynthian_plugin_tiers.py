# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: plugin tiers (zynthian_plugin_tiers)
#
# A plugin's place in the plugin menus, from plugin-db's answer for it (zynthian_plugin_qualification). Every word
# shown is plugin-db's: nothing here works out a state, a tier or where a plugin runs.
#
#   a row     <title>  <state> · <runs>[ · <standing>]     qualified · shared · within
#                                                          unqualified · alone
#                                                          refused · not-loaded
#   the detail panel: the sentences of the state, of its reason, of where it runs and of its source, the record's
#   tier (in-process, isolated) and, where the record holds it, the latency at this rate and quantum against the line.
#
# A row plugin-db has no answer for (a jalv row, which plugin-hostd's records do not judge; an entry that is no
# plugin; an entry the store does not hold) keeps its plain title.
#
# The bar is the user's setting, ZYNTHIAN_PLUGIN_BAR, one of plugin-db's three words; it filters the view and never
# changes an answer: qualified-only offers the qualified plugins only; warn-on-crashes, the default, every plugin
# that is not refused and whose files are there; load-all every plugin, the refused ones too. A refused plugin that
# is added under a bar that offers it is the user's choice: plugin-hostd is told, and runs it alone. A row whose
# plugin is not loaded as things stand (refused, absent) carries the style BELOW (the screen paints it in the
# warning colour) and comes after the others. An entry the catalogue or a refused add marked NOT_WORKING (it does
# not load at all) is listed last, greyed, with its word; the detail panel says why.
#
# A menu is ordered by state (the states in the order STATE_ORDER lists them, then in their own order), by name, or
# by the latency plugin-db answers with, a row without one after the ones that have it. hosted_only keeps the rows
# plugin-hostd runs (PH/).
#
# A plugin installed both as CLAP and as LV2 is one row, never two: formats are invisible to the user. A CLAP row and an
# LV2 row of one name are one plugin, and the one placed worse gives way: working before not working, then by state,
# then CLAP before LV2 (omx-clap-host's own format), then plugin-hostd before jalv. Rows of one format stay as they
# are: two plugins that share a name, and an LV2 plugin's jalv row beside its plugin-hostd one, which is a choice of
# engine and not of format.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import os
import logging

import plugin_db
from plugin_db import vocabulary as v

from zyngine import zynthian_plugin_hostd_protocol

BARS = tuple(v.bar.values())
BAR_TITLES = {v.bar.qualifiedOnly: "Qualified only", v.bar.warnOnCrashes: "Warn on crashes", v.bar.loadAll: "Load all"}
DEFAULT_BAR = v.bar.warnOnCrashes
SEP = " \u00b7 "
BELOW = "below"  # the style of a row whose plugin is not loaded as things stand: not greyed, but marked
ORDERS = ("state", "name", "latency")
# the order the menus list the states in: what runs as its record allows first, what is not loaded last
STATE_ORDER = (v.states.qualified, v.states.isolatedOnly, v.states.conditionsUnmet, v.states.unqualified,
               v.states.refused, v.states.absent)
NO_ANSWER_RANK = STATE_ORDER.index(v.states.unqualified)  # a row without an answer is listed with the unqualified
NOT_WORKING_RANK = len(STATE_ORDER)


def plugin_bar():
    """ZYNTHIAN_PLUGIN_BAR, one of BARS; warn-on-crashes when unset or not one of them."""
    bar = os.environ.get("ZYNTHIAN_PLUGIN_BAR", "").strip().lower() or DEFAULT_BAR
    if bar not in BARS:
        logging.warning(f"ZYNTHIAN_PLUGIN_BAR={bar} is not one of {', '.join(BARS)}: using {DEFAULT_BAR}")
        bar = DEFAULT_BAR
    return bar


def set_plugin_bar(bar, fpath=None):
    """Choose the bar: saved in the Zynthian configuration (zynconf.save_config, which also sets the environment, so the
    next plugin_bar() answers it at once, no restart), and returned. A value that is not one of BARS raises ValueError.
    A configuration that can't be written is logged and the choice holds until the next start."""
    if bar not in BARS:
        raise ValueError(f"{bar} is not one of {', '.join(BARS)}")
    try:
        import zynconf
        zynconf.save_config({"ZYNTHIAN_PLUGIN_BAR": bar}, False, fpath)
    except Exception as e:
        logging.error(f"Can't save ZYNTHIAN_PLUGIN_BAR={bar} => {e}")
        os.environ["ZYNTHIAN_PLUGIN_BAR"] = bar
    return bar


def bar_menu_options():
    """{title with its check box: bar} for the admin menu, the bar in force ticked."""
    current = plugin_bar()
    return {f"{chr(0x2612) if bar == current else chr(0x2610)} {title}": bar for bar, title in BAR_TITLES.items()}


def offered(answer, bar):
    """Whether the bar offers the plugin of this answer in the default view."""
    if bar == v.bar.qualifiedOnly:
        return answer["state"] == v.states.qualified
    if bar == v.bar.warnOnCrashes:
        return answer["state"] not in (v.states.refused, v.states.absent)
    return True


def tag(answer):
    """The words of an answer a row shows after its title: its state, where it runs and, when the record holds a
    figure at this rate and quantum, where its latency stands against the line."""
    words = [answer["state"], answer["runs"]]
    if answer.get("figures"):
        words.append(answer["figures"]["standing"])
    return SEP.join(words)


def number_text(n):
    return f"{n:.1f}" if isinstance(n, float) and n != int(n) else f"{n:.0f}"


def answer_text(answer, lang=None):
    """An answer in sentences, for the detail panel, in the device's language: the state, its reason, where it runs,
    its source, the record's tier and the latency against the line. None for no answer."""
    if not answer:
        return None
    lang = lang or zynthian_plugin_hostd_protocol.device_language()
    lines = [plugin_db.text(v.states, answer["state"], lang), plugin_db.why(answer, lang),
             plugin_db.text(v.runs, answer["runs"], lang), plugin_db.text(v.sources, answer["source"], lang)]
    if answer.get("tier"):
        lines.append(answer["tier"])
    figures = answer.get("figures")
    if figures:
        line = plugin_db.text(v.latency, figures["standing"], lang)
        if figures.get("latencyMs") is not None:
            against = "" if figures.get("lineMs") is None else f" / {number_text(figures['lineMs'])} ms"
            line += f" {number_text(figures['latencyMs'])} ms{against} ({figures['rate']} Hz, {figures['quantum']})"
        lines.append(line)
    return " ".join(lines)


def figure(answer, order):
    """The shown value a menu is sorted by, None when the row does not show it."""
    if order == "latency" and answer and answer.get("figures"):
        return answer["figures"].get("latencyMs")
    return None


def is_plugin(key):
    return key.startswith(("PH/", "JV/"))


def plugin_identity(key, info):
    """(name, format) of a plugin row: its name, case and spacing aside, None when it has none; clap or lv2."""
    name = " ".join((info.get("NAME") or "").casefold().split()) or None
    return name, "clap" if key.startswith("PH/clap:") else "lv2"


def format_rank(key):
    """CLAP before LV2, plugin-hostd before jalv: the order a tie between two rows of one plugin is broken in."""
    return 0 if key.startswith("PH/clap:") else 1 if key.startswith("PH/") else 2


def one_row_per_plugin(rows):
    """rows as menu_entries builds them, (rank, n, key, text, greyed, figure, identity), with each plugin's rows
    reduced to the best placed: working before not working, then by rank, then by format_rank, then in their own order. A row
    gives way only to a better one of the same name in the other format."""
    order = lambda r: (r[4], r[0], format_rank(r[2]), r[1])
    by_name = {}
    for row in rows:
        if row[6] is not None and row[6][0] is not None:
            by_name.setdefault(row[6][0], []).append(row)
    dropped = set()
    for group in by_name.values():
        for row in group:
            if any(order(other) < order(row) and other[6][1] != row[6][1] for other in group):
                dropped.add(id(row))
    return [row for row in rows if id(row) not in dropped]


def menu_entries(engines, answer_of, bar=DEFAULT_BAR, order="state", hosted_only=False):
    """[(key, text, style)] of one menu's engines {key: info}, in order (one of ORDERS): by state, in the order of
    STATE_ORDER and then in their own; or by name or by latency, the rows with a figure first. The plugins that are
    not loaded as things stand (refused, absent) come after the others, with their mark, when the bar offers them;
    then the entries that do not load at all, greyed. hosted_only keeps the PH rows. A plugin present in more than
    one format is one row, the best placed (one_row_per_plugin). answer_of(url) gives plugin-db's answer for a
    plugin-hostd row, None when it has none; the other rows keep their title."""
    rows = []
    marked = set()
    for n, (key, info) in enumerate(engines.items()):
        if hosted_only and not key.startswith("PH/"):
            continue
        title = info["TITLE"]
        if not is_plugin(key):
            rows.append((NO_ANSWER_RANK, n, key, title, False, None, None))
            continue
        ident = plugin_identity(key, info)
        if info.get("NOT_WORKING"):
            rows.append((NOT_WORKING_RANK, n, key, f"{title}  not working{SEP}{info['NOT_WORKING']}", True, None, ident))
            continue
        # plugin-db's records are plugin-hostd's: they do not judge a jalv row
        answer = answer_of(info.get("URL", "")) if key.startswith("PH/") else None
        if answer is None:
            if bar != v.bar.qualifiedOnly or not key.startswith("PH/"):
                rows.append((NO_ANSWER_RANK, n, key, title, False, None, ident))
            continue
        if not offered(answer, bar):
            continue
        if answer["runs"] == v.runs.notLoaded:
            marked.add(key)
        rows.append((STATE_ORDER.index(answer["state"]), n, key, f"{title}  {tag(answer)}", False,
                     figure(answer, order), ident))
    rows = one_row_per_plugin(rows)
    if order == "state":
        rows.sort(key=lambda r: r[:2])
    else:
        # the rows that load are one group, ordered by the figure; the ones not loaded and not working follow
        group = lambda r: 2 if r[4] else 1 if r[2] in marked else 0
        rows.sort(key=lambda r: (group(r), r[5] is None, r[5] or 0, r[3].lower(), r[1]))
    return [(key, text, greyed or (BELOW if key in marked else False)) for _, _, key, text, greyed, _, _ in rows]
