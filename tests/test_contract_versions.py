"""tools/contract_versions.py: the contract packages the series is built and tested against, named once in
contract-versions (`<name> [: <binary package>...]` per line), and the check that each is installed. Names only (owner
rule, 2026-11-24: no hand-kept floors): the series uses the package the channel publishes, so no line carries a
version relation; a floor is removed, never bumped."""
import os
import re

import pytest

from tools.contract_versions import parse, check, packages as packages_of

DECLARED = """# the contract the series is built and tested against
plugin-hostd-protocol : libplugin-hostd-protocol0 plugin-hostd-protocol-contract
plugin-hostd-contract
"""

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RELATION = re.compile(r"[<>=]|\b\d+\.\d+")


def test_the_declaration_parses_into_names_and_their_packages():
    assert parse(DECLARED) == ["plugin-hostd-protocol", "plugin-hostd-contract"]
    assert packages_of(DECLARED) == {"plugin-hostd-protocol": ["libplugin-hostd-protocol0", "plugin-hostd-protocol-contract"],
                                     "plugin-hostd-contract": ["plugin-hostd-contract"]}


def test_whatever_version_the_channel_serves_is_clean():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.1.0-1", "plugin-hostd-contract": "9.0.0"}) == []


def test_a_declared_package_not_installed_is_named():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.8.1"}) == ["plugin-hostd-contract is not installed"]


@pytest.mark.parametrize("line", ["plugin-hostd-protocol >= 0.8.0", "plugin-hostd-protocol >= 0.7.0 < 0.8",
                                  "plugin-hostd-protocol = 0.8.1", "plugin-hostd-protocol <= 1.0 : python3-x"])
def test_a_line_with_a_version_relation_is_refused(line):
    """A floor, a ceiling or a pin is a version this repository keeps by hand: refused, naming the line."""
    with pytest.raises(ValueError, match="line 2.*version relation"):
        parse("# x\n%s\n" % line)


def test_the_repository_names_packages_only():
    """contract-versions itself: no line carries a version relation or a version, and the names the install step
    installs are the ones the code imports or reads (the protocol and its client, the daemon's contract, omx-contract's
    readers)."""
    with open(os.path.join(ROOT, "contract-versions")) as f:
        text = f.read()
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    assert [line for line in lines if RELATION.search(line)] == []
    assert set(parse(text)) >= {"plugin-hostd-protocol", "plugin-hostd-contract", "python3-plugin-hostd-protocol",
                                "omx-contract"}


def test_the_client_the_runtime_imports_is_declared_and_carries_every_name():
    """zyngine/zynthian_plugin_hostd_protocol.py imports plugin-hostd's Python client at module load: the package that
    carries it (python3-plugin-hostd-protocol) is declared in contract-versions, and the installed client exports
    every name imported from it."""
    import ast
    import plugin_hostd_protocol

    root = ROOT
    with open(os.path.join(root, "contract-versions")) as f:
        assert "python3-plugin-hostd-protocol" in packages_of(f.read())
    with open(os.path.join(root, "zyngine", "zynthian_plugin_hostd_protocol.py")) as f:
        tree = ast.parse(f.read())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "plugin_hostd_protocol"
                for a in n.names}
    assert imported
    assert sorted(imported - set(plugin_hostd_protocol.__all__)) == []


def test_omx_contract_readers_are_imported_from_python3_omx_contract():
    """The position law and the catalog reader are omx-contract's package omx_contract (python3-omx-contract,
    omx-contract#28): imported as omx_contract.scale and omx_contract.catalog, never as a file found under
    /usr/share/omx-contract, and the package that carries them is declared in contract-versions."""
    root = ROOT
    with open(os.path.join(root, "contract-versions")) as f:
        assert "python3-omx-contract" in [p for ps in packages_of(f.read()).values() for p in ps]
    by_path = re.compile(r"^\s*(?:import|from)\s+(omx_contract_(?:scale|catalog))\b", re.M)
    found = []
    for d in ("zyngine", "zyngui", "tests"):
        for dirpath, _, files in os.walk(os.path.join(root, d)):
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(dirpath, name)
                    with open(path, encoding="utf-8", errors="replace") as f:
                        found += [f"{os.path.relpath(path, root)}: {m}" for m in by_path.findall(f.read())]
    assert found == []
