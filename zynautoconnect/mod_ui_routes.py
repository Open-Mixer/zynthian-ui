# -*- coding: utf-8 -*-
#
# The MIDI routes the autoconnect leaves to MOD-UI.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later


def drop_mod_ui_routes(required_routes, processors):
    """Take the plugins MOD-UI added out of the required routes: MOD-UI connects them itself.

    mod-host names the JACK client of a plugin effect_<n>. plugin-hostd names its clients the same way, and those are
    chain processors: their routes stay, or the plugin gets no MIDI.

    required_routes : sets of source port names indexed by destination port name, changed in place
    processors : the chain manager's processors
    """

    own = set()
    for proc in processors:
        own.add(proc.get_jackname())
        own.add(proc.get_jackname(True))
    for dst in list(required_routes):
        if dst.startswith("effect_") and dst.split(":", 1)[0] not in own:
            required_routes.pop(dst)
