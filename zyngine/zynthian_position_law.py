# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: position law of a plugin-hostd controller (zynthian_position_law)
#
# Where a control sits on its travel, 0 at the minimum and 1 at the maximum, for each scale word: the
# law is omx-contract's own (omx_contract_scale.py, which its data package installs beside the
# vectors it is held to), and this module is where the fork finds it. LAWS, effective_law,
# scale_position and scale_value are that file's; nothing of the law is written here.
#
# Only the plugin-hostd engine's controllers use it (they carry a position_law travel). Every other
# engine keeps upstream's is_logarithmic law.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 2 of the License, or any later version. See the LICENSE.txt file.
# ******************************************************************************

import os
import sys

# the directory omx-contract-data installs its Python readers in
SHARE_PATH = os.environ.get("ZYNTHIAN_OMX_CONTRACT_SHARE", "/usr/share/omx-contract")
if SHARE_PATH not in sys.path:
    sys.path.append(SHARE_PATH)

from omx_contract_scale import LAWS, effective_law, scale_position, scale_value  # noqa: E402,F401
