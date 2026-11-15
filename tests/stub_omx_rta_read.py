#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# A stand-in for omx-dsp's omx-rta-read (the RTA reader on an instance's JACK ports): it
# takes the reader's arguments and writes its JSON lines on stdout, one frame every 20 ms, with no JACK. The
# frame is fixed: --bands bands log-spaced from 20 Hz to 20 kHz, a level per tap named (--post, --pre) and, with both,
# their difference. The tests steer it by environment:
#   STUB_RTA_PIDFILE   write the stub's pid there before the first line
#   STUB_RTA_ARGV      write the arguments it was given there, one per line
#   STUB_RTA_IGNORE_TERM=1  ignore SIGTERM (only SIGKILL ends it)
#   STUB_RTA_EXIT_AFTER=<n>  exit with status 3 after n frames
#   STUB_RTA_BAD_FIRST=1     write a line that is no frame before the first one
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import json
import os
import signal
import sys
import time


def main(argv):
    post, pre, bands = [], [], 0
    k = 0
    while k < len(argv):
        if argv[k] in ("--post", "--pre", "--bands", "--name") and k + 1 < len(argv):
            {"--post": post, "--pre": pre}.get(argv[k], []).append(argv[k + 1])
            if argv[k] == "--bands":
                bands = int(argv[k + 1])
            k += 2
        else:
            k += 1
    if not (post or pre) or bands < 2:
        print("omx-rta-read: name a tap and at least two bands", file=sys.stderr)
        return 2
    if os.environ.get("STUB_RTA_ARGV"):
        with open(os.environ["STUB_RTA_ARGV"], "w") as f:
            f.write("\n".join(argv) + "\n")
    if os.environ.get("STUB_RTA_IGNORE_TERM") == "1":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if os.environ.get("STUB_RTA_PIDFILE"):
        with open(os.environ["STUB_RTA_PIDFILE"], "w") as f:
            f.write(str(os.getpid()))
    if os.environ.get("STUB_RTA_BAD_FIRST") == "1":
        print("not a frame", flush=True)
    hz = [20 * 1000 ** (b / (bands - 1)) for b in range(bands)]
    exit_after = int(os.environ.get("STUB_RTA_EXIT_AFTER", "0"))
    at = 0
    while True:
        frame = {"at": at, "rate": 48000, "hz": hz}
        if post:
            frame["post"] = {"db": [-30.0 - b % 7 for b in range(bands)], "peak": [-27.0 - b % 7 for b in range(bands)]}
        if pre:
            frame["pre"] = {"db": [-24.0 - b % 5 for b in range(bands)], "peak": [-21.0 - b % 5 for b in range(bands)]}
            frame["pre"]["db"][0] = None  # a silent band: JSON's null, -INFINITY to the renderer
        if post and pre:
            frame["diff"] = [p - q if q is not None else None for p, q in zip(frame["post"]["db"], frame["pre"]["db"])]
        try:
            print(json.dumps(frame), flush=True)
        except BrokenPipeError:
            return 0
        at += 1
        if exit_after and at >= exit_after:
            return 3
        time.sleep(0.02)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
