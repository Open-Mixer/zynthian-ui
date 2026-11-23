# -*- coding: utf-8 -*-
#
# The MIDI routes the autoconnect leaves to MOD-UI.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later


def drop_mod_ui_routes(required_routes, processors, hosted=None):
    """Take the plugins MOD-UI added out of the required routes: MOD-UI connects them itself.

    mod-host names the JACK client of a plugin effect_<n>. A plugin-hostd client carries the instance key
    plugin-hostd-protocol declares (plugin-hostd#33), whatever its name: its routes stay, or the plugin gets no MIDI;
    so do a chain processor's.

    required_routes : sets of source port names indexed by destination port name, changed in place
    processors : the chain manager's processors
    hosted : whether a client carries plugin-hostd's instance key (client name -> bool)
    """

    own = set()
    for proc in processors:
        own.add(proc.get_jackname())
        own.add(proc.get_jackname(True))
    for dst in list(required_routes):
        client = dst.split(":", 1)[0]
        if dst.startswith("effect_") and client not in own and not (hosted and hosted(client)):
            required_routes.pop(dst)
