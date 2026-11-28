# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: omx-contract's contract directory (zynthian_contract_dir)
#
# Where the owners' declarations are installed: omx-contract's contract directory, found the way plugin-hostd-protocol's
# Python client finds it (Protocol's contract_dirs): $OMX_CONTRACT_PATH, a ':' list; else the directory that client was
# installed against (its _installed record, written by its make install-python from omx-contract's contractdir); else
# `pkg-config --variable=contractdir omx-contract`. The directory has no schema-major level (omx-contract
# docs/contract-dir.md, the owner's ruling of 2026-11-25): an owner's files are <contractdir>/<owner>/..., a domain's
# document <contractdir>/<owner>/<domain>/<domain>.json. No path here is typed: the installed packages say where.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import os
import subprocess


def _pkg_config(*args):
    try:
        out = subprocess.run([os.environ.get("PKG_CONFIG", "pkg-config"), *args], capture_output=True, text=True)
    except OSError:
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def _installed_dirs():
    try:
        from plugin_hostd_protocol import _installed
    except ImportError:
        return []
    return [d for d in getattr(_installed, "CONTRACT_DIRS", ()) if d]


def contract_dirs():
    """The contract directories, in the order they are read; [] when nothing names one."""
    env = os.environ.get("OMX_CONTRACT_PATH")
    if env:
        return [d for d in env.split(":") if d]
    return _installed_dirs() or [d for d in [_pkg_config("--variable=contractdir", "omx-contract")] if d]


def find(*parts, dirs=None):
    """The first <contractdir>/<parts...> that is a file, over the contract directories; None when none holds it."""
    for d in contract_dirs() if dirs is None else dirs:
        path = os.path.join(d, *parts)
        if os.path.isfile(path):
            return path
    return None


def domain(name, dirs=None):
    """The document of a domain (`plugin-hostd/grouping`): <contractdir>/<name>/<its last segment>.json; None when no
    contract directory holds it."""
    return find(*name.split("/"), name.rsplit("/", 1)[-1] + ".json", dirs=dirs)
