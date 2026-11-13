# -*- coding: utf-8 -*-
#
# A plugin-hostd client is told by the metadata plugin-hostd-protocol declares, never by its name (plugin-hostd#33):
# each worker sets the instance key (node_metadata's "instance") on the client it opens for an instance, and the
# autoconnect and the engine read it. The JACK library is stood in for: its metadata lookups by client name.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import types
import unittest
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "..", "zynautoconnect", "hosted_nodes.py")
KEY = "http://openmixer.org/ns/plugin-hostd#instance"


def load():
    spec = importlib.util.spec_from_file_location("hosted_nodes", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jack_with(metadata, ports):
    """A JACK client and a property reader for these clients: metadata maps a client name to {key: value}; ports are
    the graph's port names"""
    jclient = types.SimpleNamespace(get_ports=lambda *a, **k: [types.SimpleNamespace(name=p) for p in ports])

    def read(_jclient, client, key):
        return metadata.get(client, {}).get(key)
    return jclient, read


class test_hosted_nodes(unittest.TestCase):

    def test_a_client_carrying_the_key_is_hosted_whatever_its_name(self):
        m = load()
        jclient, read = jack_with({"MDA Piano": {KEY: "1000"}}, [])
        self.assertEqual(m.hosted_instance(jclient, "MDA Piano", KEY, read=read), 1000)

    def test_an_effect_client_without_the_key_is_not_hosted(self):
        m = load()
        jclient, read = jack_with({}, [])
        self.assertIsNone(m.hosted_instance(jclient, "effect_3", KEY, read=read), "mod-host's own client")

    def test_a_value_that_is_no_instance_is_not_hosted(self):
        m = load()
        jclient, read = jack_with({"effect_9": {KEY: "nine"}}, [])
        self.assertIsNone(m.hosted_instance(jclient, "effect_9", KEY, read=read))

    def test_the_client_of_an_instance_is_found_by_its_key(self):
        m = load()
        jclient, read = jack_with({"effect_7": {KEY: "1000"}, "effect_1000": {}},
                                  ["effect_1000:out_1", "effect_7:out_1", "effect_7:in_1", "system:playback_1"])
        self.assertEqual(m.client_of_instance(jclient, 1000, KEY, read=read), "effect_7",
                         "the key decides, not the effect_1000 a name would suggest")
        self.assertIsNone(m.client_of_instance(jclient, 5, KEY, read=read))


if __name__ == "__main__":
    unittest.main()
