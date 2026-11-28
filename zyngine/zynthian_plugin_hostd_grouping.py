# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: plugin-hostd grouping reasons (zynthian_plugin_hostd_grouping)
#
# The reason plugin-hostd gives for a plugin its plan does not run together with its neighbours, as
# a short text for the plugin's entry. The daemon declares the reason words and their sentences: the
# domain plugin-hostd/grouping (PLUGIN_HOSTD_GROUPING_REASONS), <contractdir>/plugin-hostd/grouping/
# grouping.json as plugin-hostd-contract installs it, the contract directory found as the house readers
# find it (zynthian_contract_dir). A word the daemon declares no sentence for reads as the word itself,
# and the refusal of a whole plan is told by the name of the code the daemon refused it with.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import json
import logging

from zyngine import zynthian_contract_dir

DOMAIN = "plugin-hostd/grouping"
PLAN_REFUSED = "plan-refused"

_declared = {}  # the domain's document => {word: the daemon's sentence}


def declared(directory=None):
    """{reason word: the sentence the daemon declares for it} from the domain plugin-hostd/grouping, in the contract
    directory given or else the installed one; {} when it cannot be read."""
    path = zynthian_contract_dir.domain(DOMAIN, dirs=None if directory is None else [directory])
    if path is None:
        logging.debug("plugin-hostd's domain %s is in no contract directory", DOMAIN)
        return {}
    if path not in _declared:
        try:
            with open(path) as f:
                doc = json.load(f)
            _declared[path] = {w["const"]: w.get("x-text") or w["description"]
                               for w in doc["components"]["schemas"]["PLUGIN_HOSTD_GROUPING_REASONS"]["oneOf"]}
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            logging.debug("plugin-hostd's %s is not readable (%s)", path, e)
            return {}
    return _declared[path]


def declared_words(directory=None):
    """The reason words the daemon declares; None when its declaration cannot be read."""
    return set(declared(directory)) or None


def text(reason, error_name=None):
    """The text for a reason as plan_get gives it. 'plan-refused:<code>' is told with error_name(<code>), the
    daemon's name for the code, when the caller has one."""
    word, _, code = reason.partition(":")
    if word == PLAN_REFUSED:
        try:
            name = error_name(int(code)) if error_name else code
        except ValueError:
            name = code
        return f"Not grouped: the daemon refused the plan ({name})"
    return declared().get(word) or f"Not grouped: {word}"
