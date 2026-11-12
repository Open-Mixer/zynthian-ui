# -*- coding: utf-8 -*-
#
# The words of plugin-hostd's lines: quoted words and percent-encoded paths. "Surge XT.clap" is written by
# plugin-hostd-protocol 0.4 percent-encoded (Surge%20XT.clap) or in quotation marks, and plugin-hostd keys it by the
# path decoded.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT]
if "zyngine" not in sys.modules:
    _pkg = types.ModuleType("zyngine")
    _pkg.__path__ = [os.path.join(ROOT, "zyngine")]
    sys.modules["zyngine"] = _pkg

from zyngine import zynthian_plugin_hostd_protocol as grammar  # noqa: E402

KEY = "clap:/usr/lib/clap/Surge XT.clap#org.surge-synth-team.surge-xt"


class test_words(unittest.TestCase):

    def test_bare_and_quoted_words(self):
        self.assertEqual(grammar.words('pin_set "clap:/p/My Plugins/x.clap#id" f=1  v'), ["pin_set", "clap:/p/My Plugins/x.clap#id", "f=1", "v"])
        self.assertEqual(grammar.words(r'a "b \"c\" d" e'), ["a", 'b "c" d', "e"])

    def test_the_only_escape_is_the_quote(self):
        self.assertEqual(grammar.words(r'x "a\b"'), ["x", "a\\b"], "a backslash is a character of the word")
        self.assertEqual(grammar.quote("a\\b"), '"a\\b"')
        self.assertEqual(grammar.quote('a"b'), '"a\\"b"')
        # (a value that ends in a backslash cannot be quoted: the grammar reads \" there as a quote, never a closing one)
        for value in ("a\\b", 'a"b', "a b", "a\\b\\c d"):
            self.assertEqual(grammar.words(grammar.quote(value)), [value])

    def test_a_path_is_percent_encoded_and_back(self):
        self.assertEqual(grammar.encode_path("/c/Surge XT.clap"), "/c/Surge%20XT.clap")
        self.assertEqual(grammar.encode_path("/c/a,b=c%d\"e\\f\tg"), "/c/a%2Cb%3Dc%25d%22e%5Cf%09g")
        for path in ("/c/Surge XT.clap", "/c/100%.clap", "/c/é ü.clap", "/c/a\nb"):
            self.assertEqual(grammar.decode_path(grammar.encode_path(path)), path)
        with self.assertRaises(ValueError):
            grammar.decode_path("/c/50%.clap")

    def test_every_spelling_of_a_uri_is_one_key(self):
        for spelling in ("clap:/usr/lib/clap/Surge%20XT.clap#org.surge-synth-team.surge-xt", KEY):
            self.assertEqual(grammar.pin_key(spelling), KEY)
        self.assertEqual(grammar.pin_key("urn:amp"), "urn:amp")
        self.assertEqual(grammar.uri_word(KEY), "clap:/usr/lib/clap/Surge%20XT.clap#org.surge-synth-team.surge-xt")
        self.assertEqual(grammar.uri_word("urn:amp"), "urn:amp")


if __name__ == "__main__":
    unittest.main()
