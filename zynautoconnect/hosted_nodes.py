# -*- coding: utf-8 -*-
#
# Which JACK clients are plugin-hostd's hosted nodes, by the metadata plugin-hostd-protocol declares (node_metadata,
# from 0.5.5): each worker sets the instance key on the client it opens for an instance. A client is told by
# that key, never by the effect_ prefix its name happens to have.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later


def jack_property(jclient, client_name, key):
    """The value of one JACK metadata key on a client, by the client's name; None when there is no such client, no
    such key, or a server that keeps no metadata."""
    try:
        import jack
        lib, ffi = jack._lib, jack._ffi
        uuid_text = jclient.get_uuid_for_client_name(client_name)
    except Exception:
        return None
    uuid = ffi.new("jack_uuid_t *")
    if lib.jack_uuid_parse(uuid_text.encode(), uuid) != 0:
        return None
    value, kind = ffi.new("char **"), ffi.new("char **")
    if lib.jack_get_property(uuid[0], key.encode(), value, kind) != 0 or value[0] == ffi.NULL:
        return None
    try:
        return ffi.string(value[0]).decode("utf-8", "replace")
    finally:
        lib.jack_free(value[0])
        if kind[0] != ffi.NULL:
            lib.jack_free(kind[0])


def hosted_instance(jclient, client_name, key, read=jack_property):
    """The plugin-hostd instance a client hosts, from its instance key; None for a client that carries none."""
    value = read(jclient, client_name, key)
    if value is None or not value.isdigit():
        return None
    return int(value)


def client_of_instance(jclient, instance, key, read=jack_property):
    """The name of the client whose instance key names `instance`, or None."""
    seen = set()
    for port in jclient.get_ports():
        client = port.name.split(":", 1)[0]
        if client in seen:
            continue
        seen.add(client)
        if hosted_instance(jclient, client, key, read=read) == instance:
            return client
    return None
