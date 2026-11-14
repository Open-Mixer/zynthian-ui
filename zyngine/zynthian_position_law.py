# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: position law of a plugin-hostd controller (zynthian_position_law)
#
# Where a control sits on its travel, 0 at the minimum and 1 at the maximum, for each scale word: the
# law is omx-contract's own (omx_contract.scale, from python3-omx-contract), and this module is where
# the fork finds it. LAWS, effective_law, scale_position and scale_value are that module's; nothing of
# the law is written here.
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

from omx_contract.scale import LAWS, effective_law, scale_position, scale_value  # noqa: F401
