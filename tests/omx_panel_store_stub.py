# -*- coding: utf-8 -*-
#
# A stand-in of omx-panel's Python door to the descriptions store (omx_panel_store, python3-omx-panel-store:
# omx-panel store/python/omx_panel_store.py), for the tests: the same names and the same answers, read from entries a
# test hands it as `omx-panel-store put` takes them (tests/fixtures/plugin_hostd/<name>.stored.entry.json). It holds
# the rules the library holds only as far as a test needs them: an entry whose source is not the caller's is stale
# (absent), and the scope each open asked for is kept. test_engine_plugin_hostd's OMX_PANEL_STORE_REAL arm reads the
# same entry through the real door and library instead.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import json
import types

OK, NO_ENTRY = 0, 1
SCOPE_USER, SCOPE_SYSTEM = 0, 1


class StoreError(Exception):
    def __init__(self, code, message):
        super().__init__("%s %s" % (code, message))
        self.code, self.message = code, message


def door(entries=None, sources=None):
    """A module that stands for omx_panel_store: `entries` {(sha256, format, uri): (entry, layer)}, `sources`
    {(format, path): the source the library makes of it}. Its `opened` lists the scope of each open."""
    entries, sources, opened = dict(entries or {}), dict(sources or {}), []

    def source(fmt, path):
        try:
            return sources[(fmt, path)]
        except KeyError:
            raise StoreError("panel-store.unreadable", "no source can be made of %s as %s" % (path, fmt))

    class Store:
        def __init__(self, scope):
            self.scope = scope

        @classmethod
        def open(cls, scope=SCOPE_USER):
            opened.append(scope)
            return cls(scope)

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

        def get(self, sha256, fmt, uri, src):
            held = entries.get((sha256, fmt, uri))
            if held is None or held[0]["source"] != src:
                return None
            e, layer = held
            text = lambda v: None if v is None else json.dumps(v)  # noqa: E731
            verdict = e.get("verdict") or {}
            return {"layer": layer, "stale_edit_layer": None, "edited": e["edited"], "made_by": e["made_by"],
                    "family": e["family"], "fingerprint": e["fingerprint"], "body": text(e["body"]),
                    "repeated_groups": text(e["groups"]), "refused": e["refused"],
                    "group_outcome": verdict.get("outcome"), "group_reason": verdict.get("reason"),
                    "groups": verdict.get("groups") or [], "controls": [dict(c) for c in e["controls"]]}

    return types.SimpleNamespace(OK=OK, NO_ENTRY=NO_ENTRY, SCOPE_USER=SCOPE_USER, SCOPE_SYSTEM=SCOPE_SYSTEM,
                                 StoreError=StoreError, source=source, Store=Store, opened=opened)
