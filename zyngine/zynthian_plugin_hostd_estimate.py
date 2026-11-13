# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: plugin-hostd estimate (zynthian_plugin_hostd_estimate)
#
# What a chain will cost, as plugin-hostd's estimate verb answers it from the qualification records:
#   estimate <rate> <quantum> <plugin-ref>...  =>  resp 0 <latency_frames> <cpu_percent> <ram_bytes> <workers> <unknown_count>
# The figures are the daemon's, read by plugin-hostd's client (read_estimate); this file words them for a one-line
# footer, and asks for them off the UI thread: debounced, one request in flight, the newest question the only one answered.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import threading

UNAVAILABLE = "estimate unavailable"
DEBOUNCE = 0.25


class estimate_unavailable(Exception):
    """The daemon has no estimate verb (a plugin-hostd older than the one that brought it)."""


def reason(code):
    """Why the records cannot answer for a member, by the code plugin-hostd gives it in the list: the code's sentence
    in the device's language, from its owner's catalog; 'code <n>' for a number no owner code has."""
    from zyngine import zynthian_plugin_hostd_protocol
    return zynthian_plugin_hostd_protocol.reply_codes().sentence(code) or "code %d" % code


def footer(est):
    """'chain: +64 fr latency, 12.5 % CPU, 48.0 MB, 2 workers[, 2 unknown (member 2: no record, ...)]';
    'RAM unknown' where the daemon gives none. est: the figures as plugin-hostd's client reads them (read_estimate).
    Members are counted from 1 here."""
    ram = "RAM unknown" if est["ram_bytes"] is None else "%.1f MB" % (est["ram_bytes"] / 1e6)
    text = "chain: +%d fr latency, %.1f %% CPU, %s, %d workers" % (est["latency_frames"], est["cpu_percent"], ram,
                                                                  est["workers"])
    if est["unknown_count"]:
        text += ", %d unknown" % est["unknown_count"]
        if est["members"]:
            text += " (" + ", ".join(f"member {m['member'] + 1}: {reason(m['code'])}"
                                     for m in sorted(est["members"], key=lambda m: m["member"])) + ")"
    return text


class estimator:
    """Asks for the estimate of a list of plugin refs without blocking its caller.
    fetch(rate, quantum, refs) returns the figures or raises estimate_unavailable; any other exception is
    no figure for that question. request() waits delay seconds for the next one before asking; while a
    question is out, only the newest later one is kept. result is (key, text) for the newest answered
    question, text None for no figure; the unavailable text is given once, then None."""

    def __init__(self, fetch, delay=DEBOUNCE):
        self.fetch = fetch
        self.delay = delay
        self.lock = threading.Lock()
        self.timer = None
        self.busy = False
        self.pending = None
        self.unavailable = False
        self.said = False
        self.result = None
        self.asked = 0  # the questions that reached the daemon

    def request(self, key, rate, quantum, refs):
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.pending = (key, rate, quantum, tuple(refs))
            self.timer = threading.Timer(self.delay, self.launch)
            self.timer.daemon = True
            self.timer.start()

    def launch(self):
        with self.lock:
            if self.busy or self.pending is None:
                return  # the running worker picks the pending one up
            self.busy = True
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        while True:
            with self.lock:
                question, self.pending = self.pending, None
                if question is None:
                    self.busy = False
                    return
            key, rate, quantum, refs = question
            text = self.answer(rate, quantum, refs)
            with self.lock:
                if self.pending is None:
                    self.result = (key, text)

    def answer(self, rate, quantum, refs):
        if self.unavailable:
            return self.unavailable_text()
        self.asked += 1
        try:
            return footer(self.fetch(rate, quantum, refs))
        except estimate_unavailable:
            self.unavailable = True
            return self.unavailable_text()
        except Exception:
            return None

    def unavailable_text(self):
        if self.said:
            return None
        self.said = True
        return UNAVAILABLE

    def idle(self):
        with self.lock:
            return not self.busy and self.pending is None
