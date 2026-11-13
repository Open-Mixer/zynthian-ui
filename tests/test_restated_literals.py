# -*- coding: utf-8 -*-
#
# The mechanical half of the thin-integration check (Open-Mixer/zynthian-ui#4): tools/restated_declarations.py reads the
# contract files the owners install and refuses a literal they declare that a module of this fork writes again, one
# its allowance (tools/restated_literals.left) does not know, one the allowance still lists but the module no
# longer writes, and a root with no contract files. The rules are tested on a small trimmed contract root
# (tests/fixtures/restated_contracts); the gate on the real tree runs against the installed packages and fails,
# naming what is missing, on a desk that has none.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "tools")]

import restated_declarations as check  # noqa: E402

TOOL = os.path.join(ROOT, "tools", "restated_declarations.py")
CONTRACTS = os.path.join(HERE, "fixtures", "restated_contracts")
MODULE = "zyngine/zynthian_plugin_demo.py"  # a name SCAN matches
DB = "omx-contract/contract.d/3/plugin-db/db.json"


def run(*args, env=None):
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=env)


class test_restated_literals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        os.makedirs(os.path.join(self.tmp, "zyngine"))
        self.left = os.path.join(self.tmp, "groups.left")
        open(self.left, "w").close()
        self.allowance = os.path.join(self.tmp, "literals.left")
        self.allow("")

    def module(self, source):
        with open(os.path.join(self.tmp, MODULE), "w") as f:
            f.write(source)

    def allow(self, text):
        with open(self.allowance, "w") as f:
            f.write(text)

    def gate(self, *more):
        return run("--root", self.tmp, "--left", self.left, "--contracts", CONTRACTS,
                   "--literals-left", self.allowance, *more)

    # the gate on this tree

    def test_this_tree_restates_what_its_allowance_says(self):
        root = os.environ.get("RESTATED_CONTRACT_ROOT") or check.CONTRACT_ROOT
        out = run()
        self.assertNotEqual(out.returncode, 2, "no contract files under %s: install omx-contract-data, "
                            "plugin-hostd-protocol-contract and the owners' other contract packages, or name the "
                            "root with RESTATED_CONTRACT_ROOT\n%s" % (root, out.stderr))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("literals restated at", out.stdout)

    def test_every_scanned_module_is_one_this_fork_wrote_and_every_importer_of_one_is_scanned(self):
        scanned = set(check.scanned(ROOT))
        self.assertEqual({row[1] for row in check.TABLE} - scanned, set(), "a module of TABLE is not scanned")
        fork = re.compile(r"\b(zynthian_plugin_\w+|zynthian_panel_gestures|zynthian_omx_panel_view|omx_contract\w*|"
                          r"plugin_db\w*)\b")
        for here, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "tests", "tools")]
            for name in files:
                path = os.path.relpath(os.path.join(here, name), ROOT)
                if not name.endswith(".py") or path in scanned:
                    continue
                with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                    imports = [l for l in f if re.match(r"\s*(?:from|import)\s", l) and fork.search(l)]
                self.assertEqual(imports, [], "%s imports a module of this fork's declarations and is not in SCAN" % path)

    # what is a declared literal

    def test_a_declared_literal_is_a_value_that_declares_a_word_of_a_protocol(self):
        decl = check.declared(CONTRACTS)
        for literal, role in (("pin_set", "verb"), ("worker_list", "verb"), ("output_set", "line"),
                              ("reply.plugin-hostd.placement-invalid", "code"), ("panel.skin.api-mismatch", "code"),
                              ("load-all", "word"), ("qualified-only", "word"), ("probe-timeout", "kind set"),
                              ("rtSafety", "kind set"), ("fixed-frame", "kind list"), ("omx-clap-host", "word"),
                              ("omx-comp-kernel", "kind set"), ("plan-refused", "word")):
            self.assertIn(role, decl.get(literal, {}), literal)
        self.assertEqual(sorted(decl[literal := "qualified-only"]["word"]), [DB])

    def test_prose_keys_numbers_and_scalars_are_not_declared(self):
        decl = check.declared(CONTRACTS)
        for literal in ("Only a qualified plugin loads; see pin_set.", "The plugin cannot be placed there.",
                        "someKeyName-only", "loadAll", "placementInvalid", "never-read-scalar", "12345", "-501",
                        "PROTOCOL_NOT_FOUND", "A fixture verb", "doc-token", "text-token", "meaning-token"):
            self.assertNotIn(literal, decl, literal)

    def test_a_plain_word_or_a_short_one_is_noise_and_never_declared(self):
        decl = check.declared(CONTRACTS)
        for literal in ("add", "remove", "on", "off", "id"):
            self.assertNotIn(literal, decl, literal)
        for good in ("pin_set", "no-verdict", "rtSafety", "a.b.c", "x:y:zz"):
            self.assertTrue(check.distinctive(good), good)
        for bad in ("add", "name", "step", "on", "id", "12345", "a_b", "pin_", "-set_x", "Plain", "two words",
                    "has space-x", ""):
            self.assertFalse(check.distinctive(bad), bad)

    # what a module restates

    def test_a_literal_equal_to_a_declared_one_is_a_site(self):
        self.module('A = "load-all"\nB = {"probe-timeout": 1}\nC = ["add", "name", "off"]\nD = f"{A}-x"\n')
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s:1: 'load-all' is declared in %s" % (MODULE, DB), out.stderr)
        self.assertIn("%s:2: 'probe-timeout'" % MODULE, out.stderr)
        self.assertNotIn("'add'", out.stderr)
        self.assertNotIn("'name'", out.stderr)

    def test_a_command_line_that_starts_with_a_declared_verb_is_a_site_prose_that_starts_with_a_word_is_not(self):
        self.module('A = "pin_set %s ok"\nB = f"worker_list"\nC = "load-all of them"\nD = "the pin_set verb"\n')
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s:1: 'pin_set'" % MODULE, out.stderr)
        self.assertIn("%s:2: 'worker_list'" % MODULE, out.stderr)
        self.assertNotIn(":3:", out.stderr, "a word is a site alone, not at the head of a sentence")
        self.assertNotIn(":4:", out.stderr)

    def test_a_module_that_is_not_the_forks_is_not_scanned(self):
        os.makedirs(os.path.join(self.tmp, "zyngine"), exist_ok=True)
        with open(os.path.join(self.tmp, "zyngine", "zynthian_engine_jalv.py"), "w") as f:
            f.write('A = "load-all"\n')
        self.module("A = 1\n")
        self.allow("")
        out = self.gate()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    # the allowance

    def test_what_the_allowance_lists_is_green(self):
        self.module('A = "load-all"\nB = "load-all"\nC = "pin_set x"\n')
        self.allow("# a comment\n%s load-all 2  # two sites\n%s pin_set 1\n" % (MODULE, MODULE))
        out = self.gate()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("2 literals restated at 3 sites", out.stdout)

    def test_a_literal_restated_again_is_refused_naming_file_line_literal_and_contract(self):
        self.module('A = "load-all"\n\nB = "qualified-only"\n')
        self.allow("%s load-all 1\n" % MODULE)
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s:3: 'qualified-only' is declared in %s and written again here" % (MODULE, DB), out.stderr)
        self.assertNotIn("'load-all' is declared", out.stderr)

    def test_one_more_site_of_an_allowed_literal_is_refused(self):
        self.module('A = "load-all"\nB = "load-all"\n')
        self.allow("%s load-all 1\n" % MODULE)
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s:2: 'load-all'" % MODULE, out.stderr)
        self.assertNotIn("%s:1:" % MODULE, out.stderr)

    def test_an_allowed_literal_no_longer_written_must_lower_the_allowance(self):
        self.module('A = "load-all"\n')
        self.allow("%s load-all 1\n%s qualified-only 1\n" % (MODULE, MODULE))
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("qualified-only", out.stderr)
        self.assertIn("lower the number", out.stderr)
        self.assertNotIn("'load-all' ", out.stderr)

    def test_an_allowed_module_that_is_gone_must_lower_the_allowance(self):
        self.module("A = 1\n")
        self.allow("zyngine/zynthian_plugin_gone.py load-all 1\n")
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("zynthian_plugin_gone.py", out.stderr)
        self.assertIn("lower the number", out.stderr)

    def test_an_entry_of_a_replaced_group_must_go(self):
        # tiers: its module is in TABLE; the file of groups says nothing is left of it, so its group is replaced
        tiers = check.TIERS
        os.makedirs(os.path.join(self.tmp, os.path.dirname(tiers)), exist_ok=True)
        with open(os.path.join(self.tmp, tiers), "w") as f:
            f.write('A = "load-all"\n')
        self.allow("%s load-all 1\n" % tiers)
        with open(self.left, "w") as f:
            f.write("tiers 0\n")
        out = self.gate()
        self.assertIn("its group tiers is replaced", out.stderr)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        with open(self.left, "w") as f:
            f.write("tiers 0\nposition 0\n")
        # a group still listed in the file keeps its modules' entries
        with open(self.left, "w") as f:
            f.write("tiers 5\n")
        again = self.gate()
        self.assertNotIn("is replaced", again.stderr)

    def test_none_is_refused_while_a_literal_is_restated(self):
        self.module('A = "load-all"\n')
        out = self.gate("--none")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s:1: 'load-all' is declared in %s" % (MODULE, DB), out.stderr)

    def test_none_passes_when_nothing_is_restated(self):
        self.module("A = 1\n")
        out = self.gate("--none")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    # what is not a protocol word (D22)

    def test_the_ids_of_the_hosts_table_are_a_package_an_engine_a_worker_never_a_word(self):
        decl = check.declared(CONTRACTS)
        self.assertIn("word", decl["omx-clap-host"], "a word of another table is still one")
        for host in ("demo-hostd", "demo-worker", "demo-isolation-host"):
            self.assertNotIn(host, decl, host)
        self.module('A = "demo-hostd"\nB = ("demo-worker", "demo-isolation-host")\n')
        out = self.gate()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    # the per-site allowance: issue=<owner>/<repo>#<n>

    def test_an_entry_with_an_issue_is_green_and_says_so(self):
        self.module('A = "load-all"\nB = "pin_set x"\n')
        self.allow("%s load-all 1 issue=Open-Mixer/plugin-hostd#67\n%s pin_set 1 issue=Open-Mixer/plugin-hostd-protocol#24\n"
                   % (MODULE, MODULE))
        out = self.gate()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("2 literals restated at 2 sites", out.stdout)

    def test_an_entry_with_an_issue_stays_when_its_group_is_replaced_one_without_goes(self):
        tiers = check.TIERS
        os.makedirs(os.path.join(self.tmp, os.path.dirname(tiers)), exist_ok=True)
        with open(os.path.join(self.tmp, tiers), "w") as f:
            f.write('A = "load-all"\nB = "pin_set x"\n')
        with open(self.left, "w") as f:
            f.write("tiers 0\n")
        self.allow("%s load-all 1 issue=Open-Mixer/plugin-hostd#67\n%s pin_set 1\n" % (tiers, tiers))
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s 'pin_set' is allowed but its group tiers is replaced" % tiers, out.stderr)
        self.assertNotIn("'load-all' is allowed", out.stderr)
        self.assertNotIn("'load-all' is declared", out.stderr)

    def test_an_entry_with_an_issue_and_fewer_sites_than_it_allows_must_be_lowered(self):
        self.module('A = "load-all"\n')
        self.allow("%s load-all 2 issue=Open-Mixer/plugin-hostd#67\n" % MODULE)
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("1 sites, the allowance says 2: lower the number", out.stderr)

    def test_an_entry_with_an_issue_and_more_sites_than_it_allows_is_refused(self):
        self.module('A = "load-all"\nB = "load-all"\n')
        self.allow("%s load-all 1 issue=Open-Mixer/plugin-hostd#67\n" % MODULE)
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s:2: 'load-all'" % MODULE, out.stderr)

    def test_an_issue_that_is_not_an_owner_reference_is_refused(self):
        self.module('A = "load-all"\n')
        for bad in ("67", "#67", "plugin-hostd#67", "Open-Mixer/plugin-hostd", "Open-Mixer/plugin-hostd#", "Open-Mixer/x#0",
                    "https://x/y/issues/1"):
            self.allow("%s load-all 1 issue=%s\n" % (MODULE, bad))
            out = self.gate()
            self.assertEqual(out.returncode, 1, bad + out.stdout + out.stderr)
            self.assertIn("is not an owner reference", out.stderr, bad)

    def test_an_allowance_line_that_is_not_the_form_is_an_error(self):
        self.module('A = "load-all"\n')
        for bad in ("%s load-all 1 because\n" % MODULE, "%s load-all\n" % MODULE, "%s load-all 1 issue=a/b#1 x\n" % MODULE):
            self.allow(bad)
            out = self.gate()
            self.assertEqual(out.returncode, 2, bad + out.stdout + out.stderr)

    def test_none_lists_the_sites_an_issue_entry_allows(self):
        self.module('A = "load-all"\n')
        self.allow("%s load-all 1 issue=Open-Mixer/plugin-hostd#67\n" % MODULE)
        self.assertEqual(self.gate().returncode, 0)
        out = self.gate("--none")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("%s:1: 'load-all'" % MODULE, out.stderr)

    # the name argument of a call into the owner's library (D22)

    def test_the_name_argument_of_a_call_into_the_owner_is_no_restatement_anything_else_is(self):
        self.module('P = None\nP.code("load-all")\nP.find("load-all")\nP.name("load-all")\nP.need("load-all")\nP.encode("pin_set", 1)\n'
                    'command("pin_set", 2)\nok = 1\n')
        out = self.gate()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.module('P = None\nP.code("load-all", "qualified-only")\nP.other("load-all")\nT = ("load-all",)\n'
                    'x = "pin_set" == y\nP.call("pin_set 1")\n')
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        for line, literal in ((2, "qualified-only"), (3, "load-all"), (4, "load-all"), (5, "pin_set"), (6, "pin_set")):
            self.assertIn("%s:%d: '%s'" % (MODULE, line, literal), out.stderr)
        self.assertNotIn("%s:2: 'load-all'" % MODULE, out.stderr, "the first argument is the question to the owner")

    # the contract root

    def test_a_root_with_no_contract_files_is_an_error_naming_what_is_missing(self):
        out = run("--root", self.tmp, "--left", self.left, "--contracts", os.path.join(self.tmp, "nothing"),
                  "--literals-left", self.allowance)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        for directory in check.CONTRACT_DIRS:
            self.assertIn(directory, out.stderr)

    def test_a_root_that_lacks_one_owner_is_an_error_naming_it_alone(self):
        partial = os.path.join(self.tmp, "partial")
        shutil.copytree(CONTRACTS, partial)
        shutil.rmtree(os.path.join(partial, "omx-contract", "contract.d", "3", "plugin-hostd"))
        out = run("--root", self.tmp, "--left", self.left, "--contracts", partial, "--literals-left", self.allowance)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("in: omx-contract/contract.d/*/plugin-hostd (install", out.stderr)
        self.assertNotIn("plugin-db", out.stderr)

    def test_the_root_comes_from_the_environment_when_no_flag_names_it(self):
        self.module('A = "load-all"\n')
        self.allow("%s load-all 1\n" % MODULE)
        env = dict(os.environ, RESTATED_CONTRACT_ROOT=CONTRACTS)
        out = run("--root", self.tmp, "--left", self.left, "--literals-left", self.allowance, env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        env["RESTATED_CONTRACT_ROOT"] = os.path.join(self.tmp, "nothing")
        out = run("--root", self.tmp, "--left", self.left, "--literals-left", self.allowance, env=env)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)

    def test_no_contracts_says_so_and_checks_the_hand_listed_groups_alone(self):
        self.module('A = "load-all"\n')
        out = run("--root", self.tmp, "--left", self.left, "--no-contracts")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("NOT checked", out.stderr)
        self.assertNotIn("literals restated", out.stdout)

    def test_an_allowance_that_cannot_be_read_is_an_error(self):
        out = run("--root", self.tmp, "--left", self.left, "--contracts", CONTRACTS,
                  "--literals-left", os.path.join(self.tmp, "absent.left"))
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("absent.left", out.stderr)

    def test_a_contract_file_that_is_not_json_is_an_error(self):
        broken = os.path.join(self.tmp, "broken")
        shutil.copytree(CONTRACTS, broken)
        with open(os.path.join(broken, "omx-panel", "schema", "codes.json"), "w") as f:
            f.write("{not json")
        out = run("--root", self.tmp, "--left", self.left, "--contracts", broken, "--literals-left", self.allowance)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("codes.json cannot be read", out.stderr)


if __name__ == "__main__":
    unittest.main()
