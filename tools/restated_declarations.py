#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# tools/restated_declarations.py [--root DIR] [--left FILE] [--none]
#
# Lists what this fork still writes in Python that an OpenMixer library declares (Open-Mixer/zynthian-ui#4, thin
# integration: shared owners only). A row of TABLE is one name a module defines at its top level, or one pattern of
# its lines, with the group it belongs to; a group is replaced, in one pull request, by calls to its owner's library,
# and its rows are then gone from the modules.
#
# tools/restated_declarations.left holds, per group, how many rows are left: the number only falls. Exit 0 when what
# is left is what the file says; exit 1 when a group has more rows left than the file says (something was restated
# again), fewer (lower the number in the same change), or the file names a group TABLE does not have. --none is the
# end of #4: exit 1 while any row is left.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEFT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restated_declarations.left")

PROTOCOL = "zyngine/zynthian_plugin_hostd_protocol.py"
ENGINE = "zyngine/zynthian_engine_plugin_hostd.py"
CATALOGUE = "zyngine/zynthian_plugin_hostd_catalogue.py"
QUALIFICATION = "zyngine/zynthian_plugin_qualification.py"
TIERS = "zyngine/zynthian_plugin_tiers.py"
ESTIMATE = "zyngine/zynthian_plugin_hostd_estimate.py"
POSITION = "zyngine/zynthian_position_law.py"
PANEL = "zyngine/zynthian_omx_panel_view.py"

# group: (its owner, what replaces it)
GROUPS = {
    "words": ("plugin-hostd", "plugin_hostd_protocol: words, quote, encode_path, decode_path, uri_word, pin_key"),
    "codes": ("plugin-hostd", "plugin_hostd_protocol.Protocol: code, name, sentence"),
    "verbs": ("plugin-hostd", "plugin_hostd_protocol.Protocol.encode"),
    "replies": ("plugin-hostd", "plugin_hostd_protocol.Protocol.parse"),
    "scan": ("omx-clap-core", "the scanner's own reader of its output"),
    "records": ("plugin-db", "plugin_db: the record reader"),
    "tiers": ("plugin-db", "plugin_db: the verdict and its standing"),
    "position": ("omx-contract", "omx-contract's Python scale"),
    "gestures": ("omx-panel", "omx-panel's gesture declaration"),
    "compare": ("omx-panel", "omx-panel's compare slots"),
}

# (group, file, a top-level name the file defines) or (group, file, None, a pattern of its lines)
TABLE = (
    [("words", PROTOCOL, n) for n in ("CLAP_PREFIX", "ESCAPE", "EXCLUDED", "words", "quote", "escaped", "encode_path",
                                      "decode_path", "split_uri", "uri_word", "pin_key")] +
    [("codes", PROTOCOL, n) for n in ("HOST_FILE", "TABLE_FILE", "owner_sources", "protocol")] +
    [("verbs", ENGINE, None, r"""\b(?:call|send|send_quiet|append)\(\s*f?["'][a-z][a-z_]*[ "']"""),
     ("verbs", ENGINE, None, r"""(?:\breturn |= \[)f["'][a-z][a-z_]* \{""")] +
    [("replies", ENGINE, n) for n in ("ISOLATE_REASONS", "RETRY_REASONS", "parse_segments", "parse_reasons")] +
    [("replies", ESTIMATE, "parse")] +
    [("scan", CATALOGUE, n) for n in ("CLAP_PLUGIN_RE", "CLAP_PARAM_RE", "parse_clap_scan")] +
    [("records", QUALIFICATION, n) for n in ("DOCUMENT_FORMAT", "RECORD_SCHEMA", "PIN_VERDICTS", "CRASH_CODES",
                                             "UNSOAKED_CODE", "PROBE_OK", "PROBE_CRASHED", "PROBE_TIMEOUT",
                                             "DIMENSIONS", "read_pins", "record_key", "record_entry", "file_entries",
                                             "read_documents")] +
    [("tiers", TIERS, n) for n in ("LIVE_MAX_MS", "RANK", "CAUSES", "WHAT", "place")] +
    [("position", POSITION, n) for n in ("LAWS", "effective_law", "scale_position", "scale_value")] +
    [("gestures", PANEL, n) for n in ("WORDS", "CURVE_KINDS", "CURVE_ROLES")] +
    [("compare", ENGINE, n) for n in ("COMPARE_SLOTS", "COMPARE_QUEUE")]
)


def defined(source):
    """The names a module defines at its top level: its functions, classes and assigned names."""
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
    return names


def left(root=ROOT, table=TABLE):
    """The rows still in the modules: [(group, file, what)], a pattern once per line it matches."""
    out, sources = [], {}
    for row in table:
        group, path = row[0], row[1]
        if path not in sources:
            try:
                with open(os.path.join(root, path), encoding="utf-8") as f:
                    text = f.read()
                sources[path] = (text, defined(text))
            except OSError:
                sources[path] = ("", set())  # a module that is gone restates nothing
        text, names = sources[path]
        if row[2] is not None:
            if row[2] in names:
                out.append((group, path, row[2]))
        else:
            pattern = re.compile(row[3])
            out += [(group, path, "line %d: %s" % (n, line.strip()))
                    for n, line in enumerate(text.splitlines(), 1) if pattern.search(line)]
    return out


def read_left(path=LEFT):
    """{group: rows left} as the file says it: `<group> <count>` lines, # comments."""
    counts = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].split()
            if line:
                counts[line[0]] = int(line[1])
    return counts


def check(rows, counts):
    """What is wrong between the rows left and the file's counts: a list of sentences, empty when they agree."""
    wrong = []
    found = {}
    for group, _, _ in rows:
        found[group] = found.get(group, 0) + 1
    for group in sorted(set(counts) - set(GROUPS)):
        wrong.append("%s is not a group of this check" % group)
    for group in GROUPS:
        have, said = found.get(group, 0), counts.get(group, 0)
        if have > said:
            wrong.append("%s: %d left, the file says %d: a declaration of %s is restated again" % (
                group, have, said, GROUPS[group][0]))
        elif have < said:
            wrong.append("%s: %d left, the file says %d: lower the number in this change" % (group, have, said))
    return wrong


def main(argv):
    root, left_file, none = ROOT, LEFT, False
    args = argv[1:]
    while args:
        a = args.pop(0)
        if a == "--none":
            none = True
        elif a in ("--root", "--left") and args:
            root, left_file = (args.pop(0), left_file) if a == "--root" else (root, args.pop(0))
        else:
            print("usage: restated_declarations.py [--root DIR] [--left FILE] [--none]", file=sys.stderr)
            return 2
    rows = left(root)
    for group in GROUPS:
        mine = [r for r in rows if r[0] == group]
        if mine:
            print("%s (%s; replaced by %s): %d left" % (group, GROUPS[group][0], GROUPS[group][1], len(mine)))
            for _, path, what in mine:
                print("  %s  %s" % (path, what))
    wrong = ["%d restated declarations are left" % len(rows)] if none and rows else [] if none else \
        check(rows, read_left(left_file))
    for w in wrong:
        print("restated-declarations: %s" % w, file=sys.stderr)
    if not wrong:
        print("restated-declarations: %d left in %d groups, as %s says" % (
            len(rows), len({r[0] for r in rows}), os.path.basename(left_file)) if rows else
            "restated-declarations: none left")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
