#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# tools/restated_declarations.py [--root DIR] [--left FILE] [--none]
#                                [--contracts DIR | --no-contracts] [--literals-left FILE]
#
# The plugin-hostd engine and its helper modules talk to libraries that declare their own words: plugin-hostd's
# protocol client, omx-contract, omx-panel and plugin-db each install the commands, codes and tables they define. A
# copy of one of those declarations in this tree goes stale when the library changes, so the modules are meant to
# ask the library instead. This check lists what the modules still write themselves. A row of TABLE is one name a
# module defines at its top level, or one pattern of its lines, with the group it belongs to; a group is replaced,
# in one change, by calls to its owner's library, and its rows are then gone from the modules.
#
# tools/restated_declarations.left holds, per group, how many rows are left: the number only falls. Exit 0 when what
# is left is what the file says; exit 1 when a group has more rows left than the file says (something was restated
# again), fewer (lower the number in the same change), or the file names a group TABLE does not have. --none asks
# for nothing left: exit 1 while any row is left.
#
# The second half is mechanical: it reads the contract files the owners install and refuses what the hand-listed
# TABLE does not know about. It collects the literals the owners declare and scans the plugin-hostd modules for a
# string literal equal to one.
#
#   A declared literal is the string value of a key that declares a word of a protocol: `verb` (a command), `line`
#   (a feedback line), `code` (a reply or refusal code), `word` (a word of a vocabulary), and the members of a
#   contract table of kind `set` (its `ids`) or `list` (its `values`), in every .json of the owners' directories
#   (CONTRACT_DIRS under the contract root). Keys alone, prose (`doc`, `text`, `meaning`) and numbers are not.
#   A string literal of a module restates it when it is equal to a declared literal, or when it is a command line
#   (it has a space) whose first word is a declared `verb` or `line`. One place is not a restatement: the NAME argument of a call into the owner's library, the first argument of `command`, `encode`,
#   `code`, `name`, `find` or `need` (the protocol client, reply_codes, and the engine's `command`, which is the
#   client's encode): naming the verb or the code is how the owner is asked. Anywhere else a declared literal is red: a line
#   built as text, a table of codes, a comparison.
#
#   Noise rule: a literal counts only when it is DISTINCTIVE: at least MIN_LENGTH characters, one token (letters
#   and digits) joined by `.`, `-`, `_` or `:`, or written in camelCase (pin_set, worker_list, hosting.stability.
#   unsoaked, no-verdict, rtSafety). A plain word (on, off, id, name, step, select, chain) is the language's and the
#   hand-listed groups above carry the ones that matter; generic words would make the gate red on every `"name"`.
#
#   The modules scanned are the plugin-hostd modules (SCAN, and every module of TABLE) and the Zynthian modules that
#   call into them: the rest of zyngine and zyngui speaks its own formats (mod-host's midi_learn, a snapshot's
#   audio_in). test_restated_literals keeps SCAN honest: a module that imports one of the plugin-hostd modules must
#   be in it.
#
#   Two more things are not protocol words: the ids of the hosts table (HOST_TABLES, the
#   `VERB_HOSTS` table of omx-contract's verbs.json: plugin-hostd, omx-clap-host, mod-host, and plugin-db's
#   `PLUGIN_DB_ISOLATION_HOSTS`, the same ids), which name a package, an engine and a worker, never a word on the
#   wire; they are left out of the declared literals.
#
# tools/restated_literals.left is the allowance: `<module> <literal> <sites> [issue=<owner>/<repo>#<n> | reason=<text>]`,
# a literal that is still restated today; a reason is the rest of the line. Red when a literal is restated that the
# file does not allow (a declaration restated again), when the file allows more than is there (lower it in the same
# change, an issue= or reason= entry too), when a module of a group TABLE says is replaced still has an entry with
# NEITHER an issue= nor a reason=, when an issue= is not a well-formed owner reference, and with --none while
# anything is found. Red names file:line, the literal and the contract file. An empty reason=, or both on one line,
# is not the form (exit 2).
# An entry with issue= or reason= is a PER-SITE allowance: the site stays until its owner declares what it needs (a
# verb or a code a module compares, a table the owner has to publish), so it does not depend on the module's group
# being replaced, and it is counted per module and literal, not by line, so unrelated edits leave it alone. The issue
# names the owner's change that removes it; a reason says what the owner is to provide.
#
# The contract root is --contracts DIR, else $RESTATED_CONTRACT_ROOT, else /usr/share. A root that lacks one of
# the owners' directories (or holds no .json there) is an error, exit 2, with the directory named: there is no silent
# fallback to the hand-listed check. --no-contracts says "no contracts here": the hand-listed check alone runs and
# says out loud that the literals were not checked.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import ast
import fnmatch
import glob
import json
import os
import re
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEFT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restated_declarations.left")
LITERALS_LEFT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restated_literals.left")
CONTRACT_ROOT = os.environ.get("RESTATED_CONTRACT_ROOT") or "/usr/share"

# where the owners install their declarations, under the contract root: omx-contract's contract directory holds one
# directory per owner (omx-contract, omx-clap-core, omx-dsp, omx-plugins, plugin-db, plugin-hostd,
# plugin-hostd-protocol; the * is the contract's major), plugin-hostd-protocol installs its own command table, omx-panel its schema
CONTRACT_DIRS = tuple("omx-contract/contract.d/*/" + owner for owner in (
    "omx-contract", "omx-clap-core", "omx-dsp", "omx-plugins", "plugin-db", "plugin-hostd", "plugin-hostd-protocol")
) + ("plugin-hostd-protocol", "omx-panel/schema")
HOST_TABLES = ("VERB_HOSTS", "PLUGIN_DB_ISOLATION_HOSTS")  # tables whose ids name a package, an engine or a worker: not words of a protocol
REASON = object()  # an allowance that says why in words: it stands where an issue= reference would
ISSUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*#[1-9][0-9]*$")
ROLE_KEYS = ("verb", "line", "code", "word")
COMMAND_ROLES = ("verb", "line")
TABLE_MEMBERS = {"set": "ids", "list": "values"}
MIN_LENGTH = 5
DISTINCT = re.compile(r"^(?:[A-Za-z][A-Za-z0-9]*(?:[._:\-][A-Za-z0-9]+)+|[a-z][a-z0-9]*(?:[A-Z][a-z0-9]+)+)$")

# the plugin-hostd modules, besides every module of TABLE
SCAN = ("zyngine/zynthian_plugin_*.py", "zyngine/zynthian_engine_plugin_hostd*.py", "zyngine/zynthian_omx_*.py",
        "zyngine/zynthian_panel_*.py", "zyngine/zynthian_position_law.py",
        "zyngine/zynthian_touch_layer.py", "zyngine/ctrldev/zynthian_ctrldev_base_surface.py",
        "zynautoconnect/mod_ui_routes.py", "zyngui/zynthian_widget_omx_*.py",
        # the Zynthian modules that call into them
        "zyngine/zynthian_chain_manager.py", "zynautoconnect/zynthian_autoconnect.py", "zyngui/zynthian_gui_admin.py", "zyngui/zynthian_gui_engine.py")

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


class NoContracts(Exception):
    """The contract root lacks what the owners install: the literals cannot be checked."""


def distinctive(literal):
    """The noise rule: long enough, and one token joined by . - _ : or written in camelCase."""
    return len(literal) >= MIN_LENGTH and bool(DISTINCT.match(literal))


def collect(node, found, rel):
    """Add to found {literal: {role: [contract files]}} what one parsed .json declares."""
    if isinstance(node, dict):
        kind = node.get("kind")
        members = TABLE_MEMBERS.get(kind) if isinstance(kind, str) else None
        for value in (node.get(members) or []) if members else []:
            if isinstance(value, str):
                found.setdefault(value, {}).setdefault("kind " + kind, set()).add(rel)
        for key, value in node.items():
            if key in HOST_TABLES:
                continue  # a host's id is its package, engine or worker, not a word on the wire
            if key in ROLE_KEYS and isinstance(value, str):
                found.setdefault(value, {}).setdefault(key, set()).add(rel)
            collect(value, found, rel)
    elif isinstance(node, list):
        for value in node:
            collect(value, found, rel)


def declared(contracts):
    """{literal: {role: {contract files}}} of the distinctive literals the owners declare under the contract root.
    Raises NoContracts when the root, or one of the owners' directories, holds no .json."""
    found, empty = {}, []
    for directory in CONTRACT_DIRS:
        count = 0
        for top in sorted(glob.glob(os.path.join(glob.escape(contracts), directory))):
            for here, dirs, files in os.walk(top):
                dirs[:] = sorted(d for d in dirs if d not in ("catalogs", "node_modules", "ts", "fixtures"))
                for name in sorted(files):
                    if name.endswith(".json"):
                        path = os.path.join(here, name)
                        try:
                            with open(path, encoding="utf-8") as f:
                                collect(json.load(f), found, os.path.relpath(path, contracts))
                            count += 1
                        except (OSError, ValueError) as e:
                            raise NoContracts("%s cannot be read: %s" % (path, e))
        if not count:
            empty.append(directory)
    if empty:
        raise NoContracts("no contract files under %s in: %s (install the owners' packages, name another root with "
                          "--contracts, or say --no-contracts)" % (contracts, ", ".join(empty)))
    return {lit: roles for lit, roles in found.items() if distinctive(lit)}


def scanned(root=ROOT, table=TABLE):
    """The modules the literal scan reads: every module of TABLE and every module SCAN names, that exist."""
    paths = {row[1] for row in table}
    for pattern in SCAN:
        directory = os.path.dirname(pattern)
        try:
            names = os.listdir(os.path.join(root, directory))
        except OSError:
            continue
        paths.update(os.path.join(directory, n) for n in names if fnmatch.fnmatch(os.path.join(directory, n), pattern))
    return sorted(p for p in paths if os.path.isfile(os.path.join(root, p)))


NAME_CALLS = ("command", "encode", "code", "name", "find", "need")  # the name argument of these asks the owner


def asked(tree):
    """The ids of the string constants that are the first argument of a call into the owner's library (NAME_CALLS)."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            f = n.func
            if (f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None) in NAME_CALLS:
                out.add(id(n.args[0]))
    return out


def strings(text):
    """[(line, value)] of the string literals of a module, the pieces of an f-string among them; the name argument of a
    call into the owner's library (asked) is left out."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    skip = asked(tree)
    return sorted((n.lineno, n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip)


def restated(root, decl, paths=None):
    """The sites where a module writes what an owner declares: [(module, line, literal, contract file)]."""
    out = []
    for path in scanned(root) if paths is None else paths:
        with open(os.path.join(root, path), encoding="utf-8") as f:
            text = f.read()
        for line, value in strings(text):
            hit = value if value in decl else None
            if hit is None and " " in value.strip():
                first = value.split()[0]
                if first in decl and any(r in decl[first] for r in COMMAND_ROLES):
                    hit = first
            if hit is not None:
                roles = decl[hit]
                out.append((path, line, hit, sorted({f for files in roles.values() for f in files})[0]))
    return out


def read_literals(path=LITERALS_LEFT):
    """{(module, literal): (sites, issue)} as the file says it: `<module> <literal> <sites> [issue=<ref> | reason=<text>]`
    lines, # comments; issue is None with neither, the reference itself with issue=, REASON with reason=. The
    reference is checked by check_literals, not here."""
    allowed = {}
    form = "%s: not `<module> <literal> <sites> [issue=<ref> | reason=<text>]`: %s"
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = re.split(r"(?:^|\s)#", line)[0].split()  # a comment starts at a # that opens a word: issue=o/r#4 is not one
            if not line:
                continue
            if len(line) >= 4 and line[3].startswith("reason="):
                reason = " ".join([line[3][len("reason="):]] + line[4:]).strip()
                if not reason or any(w.startswith(("issue=", "reason=")) for w in line[4:]):
                    raise ValueError(form % (path, " ".join(line)))
                allowed[(line[0], line[1])] = (int(line[2]), REASON)
                continue
            if len(line) not in (3, 4) or (len(line) == 4 and not line[3].startswith("issue=")):
                raise ValueError(form % (path, " ".join(line)))
            allowed[(line[0], line[1])] = (int(line[2]), line[3][len("issue="):] if len(line) == 4 else None)
    return allowed


def check_literals(sites, allowed, counts, table=TABLE, root=ROOT):
    """What is wrong between the sites found and the allowance: a list of sentences, empty when they agree."""
    wrong, found, where = [], {}, {}
    for module, line, literal, source in sites:
        found[(module, literal)] = found.get((module, literal), 0) + 1
        where.setdefault((module, literal), []).append((line, source))
    groups = {}
    for row in table:
        groups.setdefault(row[1], set()).add(row[0])
    for key in sorted(set(found) | set(allowed)):
        have, (said, issue) = found.get(key, 0), allowed.get(key, (0, None))
        module, literal = key
        if issue is not None and issue is not REASON and not ISSUE.match(issue):
            wrong.append("%s %r: issue=%s is not an owner reference (<owner>/<repo>#<number>)" % (module, literal, issue))
        if have > said:
            for line, source in where[key][said:] if said else where[key]:
                wrong.append("%s:%d: %r is declared in %s and written again here: read it from its owner" % (
                    module, line, literal, source))
        elif have < said:
            wrong.append("%s %r: %d sites, the allowance says %d: lower the number in this change" % (
                module, literal, have, said))
        if said and issue is None and module in groups and not any(counts.get(g) for g in groups[module]):
            wrong.append("%s %r is allowed but its group %s is replaced: remove the entry in this change, or name the "
                         "owner's issue (issue=<owner>/<repo>#<n>) or say why it stays (reason=<what the owner is to "
                         "provide>)" % (module, literal, "/".join(sorted(groups[module]))))
    return wrong


def main(argv):
    root, left_file, none = ROOT, LEFT, False
    contracts, no_contracts, literals_file = CONTRACT_ROOT, False, LITERALS_LEFT
    args = argv[1:]
    while args:
        a = args.pop(0)
        if a == "--none":
            none = True
        elif a == "--no-contracts":
            no_contracts = True
        elif a in ("--root", "--left", "--contracts", "--literals-left") and args:
            value = args.pop(0)
            if a == "--root":
                root = value
            elif a == "--left":
                left_file = value
            elif a == "--contracts":
                contracts = value
            else:
                literals_file = value
        else:
            print("usage: restated_declarations.py [--root DIR] [--left FILE] [--none] "
                  "[--contracts DIR | --no-contracts] [--literals-left FILE]", file=sys.stderr)
            return 2
    sites = []
    if not no_contracts:
        try:
            decl = declared(contracts)
        except NoContracts as e:
            print("restated-declarations: %s" % e, file=sys.stderr)
            return 2
        sites = restated(root, decl)
        print("restated-literals: %d declared literals read under %s, %d sites in %d modules" % (
            len(decl), contracts, len(sites), len({s[0] for s in sites})))
    rows = left(root)
    for group in GROUPS:
        mine = [r for r in rows if r[0] == group]
        if mine:
            print("%s (%s; replaced by %s): %d left" % (group, GROUPS[group][0], GROUPS[group][1], len(mine)))
            for _, path, what in mine:
                print("  %s  %s" % (path, what))
    for module, line, literal, source in sites:
        print("  %s:%d  %r  declared in %s" % (module, line, literal, source))
    try:
        counts = read_left(left_file)
        allowed = {} if none or no_contracts else read_literals(literals_file)
    except (OSError, ValueError) as e:
        print("restated-declarations: the ledger cannot be read: %s" % e, file=sys.stderr)
        return 2
    if none:
        wrong = (["%d restated declarations are left" % len(rows)] if rows else []) + \
                ["%s:%d: %r is declared in %s" % (m, n, lit, src) for m, n, lit, src in sites]
    else:
        wrong = check(rows, counts)
        if not no_contracts:
            wrong += check_literals(sites, allowed, counts)
    for w in wrong:
        print("restated-declarations: %s" % w, file=sys.stderr)
    if no_contracts:
        print("restated-declarations: --no-contracts: the owners' literals were NOT checked", file=sys.stderr)
    if not wrong:
        print("restated-declarations: %d left in %d groups, as %s says" % (
            len(rows), len({r[0] for r in rows}), os.path.basename(left_file)) if rows else
            "restated-declarations: none left")
        if not no_contracts:
            print("restated-declarations: %d literals restated at %d sites, as %s says" % (
                len({(s[0], s[2]) for s in sites}), len(sites), os.path.basename(literals_file)))
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
