# What tools/restated_declarations.py counts as a declared word

The PH modules ask their libraries for every word the libraries declare (a verb, a reply code, a word of a
vocabulary) instead of keeping a copy. `tools/restated_declarations.py` reads the contract files the libraries
install and reports a string literal of a PH module that equals one of those words. Two kinds of string are not
counted as a library's word, and each is a ruling the tool reads as code; this file is where they are written down.

Status: RULED by the owner. D22 on 2026-11-13; the external-standard ruling on 2026-11-23.

## D22 (2026-11-13): asking is not restating, and a host's id is not a word

- The first argument of a call into the owner's library (`command`, `encode`, `code`, `name`, `find`, `need`)
  names the verb or the code the owner is asked for. That is how the owner is asked, so it is not a copy.
  Anywhere else, a declared literal counts: a line built as text, a table of codes, a comparison.
- The ids of a hosts table (`VERB_HOSTS`, `PLUGIN_DB_ISOLATION_HOSTS`) name a package, an engine or a worker,
  never a word on the wire, so they are left out of the declared words.
- Where the gate reads it: `NAME_CALLS` and `HOST_TABLES` in `tools/restated_declarations.py`.

## A word an owner only mirrors from an external published standard (2026-11-23)

- Ruling (owner, 2026-11-23, option (a)): the gate leaves out a word an owner only mirrors from an external
  published standard, as D22 leaves out host ids. The standard owns such a word, and the library only restates it.
  A module that uses it (the CLAP plugin features of `clap/plugin-features.h` in the catalogue, say) is quoting the
  standard and does not copy a library's declaration.
- How the gate knows a mirror: from the owner's domain itself, by omx-contract's existing marker. An item of
  `"x-kind": "terms"` is "a format's terms as one specification or header states them" (omx-contract's
  `schema/domain.schema.json`, 3.21.0). Such an item must name the standard (`x-spec`, the specification's URI or
  the header's path) together with `x-format` and `x-version`. The gate leaves out every member of such an item, and
  nothing else: an item without `x-spec` is not a mirror. A word that a mirror and an owner item both declare is
  still the owner's, and a copy of it still counts.
- Where the gate reads it: `MIRROR_KIND` and `mirrors()` in `tools/restated_declarations.py`.
- Proof that it holds: tests/test_restated_literals.py puts a mirrored word in a PH module, and the gate stays
  green. The same word in an owner item turns the gate red. A mirror item that drops its `x-spec`, or whose words
  move to a plain item, turns them red again.
