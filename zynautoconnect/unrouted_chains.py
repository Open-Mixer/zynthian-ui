# -*- coding: utf-8 -*-
#
# The chains the audio autoconnect cannot route, said once.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import logging


def say_unrouted(chains, said):
    """Name the chains with a sound source and no mixer strip: the audio autoconnect routes a chain only through its
    strip, so their outputs stay unconnected.

    Each chain is named once while it stays so, not at every autoconnect; one that gets a strip and loses it again is
    named again.

    chains : the chain manager's chains, indexed by chain ID
    said : the IDs named already, kept by the caller between calls and changed in place
    Returns : the IDs named by this call
    """

    unrouted = {chain_id for chain_id, chain in chains.items() if chain.synth_slots and chain.zynmixer_proc is None}
    said.intersection_update(unrouted)
    named = sorted(unrouted - said)
    for chain_id in named:
        logging.warning(f"Audio autoconnect: chain {chain_id} has no mixer strip, so its outputs are not connected")
    said.update(named)
    return named
