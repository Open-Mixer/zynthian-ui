# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: plugin-hostd grouping reasons (zynthian_plugin_hostd_grouping)
#
# The reason plugin-hostd gives for a plugin its plan does not run together with its neighbours, as
# a short text for the plugin's entry. The daemon declares the reason words in its domain plugin-hostd/grouping
# (in omx-contract's contract directory), each with its sentence; the client of its protocol gives them as
# constants (GroupingReason), which is what a reason is compared with here. A word the daemon declares
# with no sentence reads as the word itself, and the refusal of a whole plan is told by the name of the
# code the daemon refused it with.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import os
import json
import logging

from zyngine.zynthian_plugin_hostd_protocol import GroupingReason

CONTRACT_PATH = "/usr/share/omx-contract/contract.d"
# the daemon's domain plugin-hostd/grouping (plugin-hostd-contract 0.21.0 on): <contract dir>/plugin-hostd/grouping/
DOMAIN = ("plugin-hostd", "grouping", "grouping.json")
ITEM = "PLUGIN_HOSTD_GROUPING_REASONS"

_declared = {}  # contract directories => {word: the daemon's sentence}


def contract_dirs():
    """The contract directories, in the order they are read: OMX_CONTRACT_PATH's, else the installed one."""
    return tuple(d for d in (os.environ.get("OMX_CONTRACT_PATH") or CONTRACT_PATH).split(":") if d)


def declared(contract=None):
    """{reason word: the sentence the daemon declares for it}: the words of PLUGIN_HOSTD_GROUPING_REASONS in the
    domain plugin-hostd/grouping of the first contract directory that holds it (contract, else contract_dirs()),
    each with its description; {} when it cannot be read."""
    dirs = (contract,) if contract else contract_dirs()
    if dirs not in _declared:
        path = next((p for p in (os.path.join(d, *DOMAIN) for d in dirs) if os.path.isfile(p)), None)
        try:
            if path is None:
                raise OSError("no %s in %s" % (os.path.join(*DOMAIN), ", ".join(dirs)))
            with open(path) as f:
                doc = json.load(f)
            _declared[dirs] = {w["const"]: w["description"] for w in doc["components"]["schemas"][ITEM]["oneOf"]}
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            logging.debug("plugin-hostd's domain plugin-hostd/grouping is not readable (%s)", e)
            return {}
    return _declared[dirs]


def declared_words(contract=None):
    """The reason words the daemon declares; None when its declaration cannot be read."""
    return set(declared(contract)) or None


def text(reason, error_name=None):
    """The text for a reason as plan_get gives it. 'plan-refused:<code>' is told with error_name(<code>), the
    daemon's name for the code, when the caller has one."""
    word, _, code = reason.partition(":")
    if word == GroupingReason.PLAN_REFUSED:
        try:
            name = error_name(int(code)) if error_name else code
        except ValueError:
            name = code
        return f"Not grouped: the daemon refused the plan ({name})"
    return declared().get(word) or f"Not grouped: {word}"
