"""tools/contract_versions.py: the contract versions the series is built and tested against, declared once in
contract-versions (`<package> >= <floor>` per line), and the check that what is installed reaches them. Floors only
(%7's ruling): no ceiling on our own packages, so a newer release the channel serves is never a red here; an installed
version below its floor (the series cut against an older contract) is named, never read as a failing test."""
import os

import pytest

from tools.contract_versions import parse, check, packages as packages_of

DECLARED = """# the contract the series is built and tested against
plugin-hostd-protocol >= 0.7.0
plugin-hostd-contract >= 0.20.8
"""

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def test_the_declaration_parses_into_floors():
    assert parse(DECLARED) == {"plugin-hostd-protocol": "0.7.0", "plugin-hostd-contract": "0.20.8"}


def test_an_installed_set_at_the_floors_is_clean():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.7.0-1", "plugin-hostd-contract": "0.20.8-1"}) == []


def test_a_newer_release_than_any_former_ceiling_is_clean():
    # the Pi's red (runs 44797059610, 44797067216, 44797088155, 44799607252): 0.7.0 read "at or above the declared
    # ceiling 0.6"; a release above the floor is the series' contract, whatever its number
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "1.0.0-1", "plugin-hostd-contract": "0.21.0"}) == []


def test_below_the_floor_is_named():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.6.0-1", "plugin-hostd-contract": "0.20.8"}) == [
        "plugin-hostd-protocol 0.6.0-1 is below the declared floor 0.7.0"]


def test_a_declared_package_not_installed_is_named():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.7.0"}) == ["plugin-hostd-contract is not installed"]


def test_a_line_that_is_not_a_floor_is_an_error():
    with pytest.raises(ValueError, match="line 2"):
        parse("# x\nplugin-hostd-protocol 0.7.0\n")


def test_a_ceiling_is_refused():
    """A ceiling on our own package is the bound the ruling dropped: a line that carries one is an error naming it."""
    with pytest.raises(ValueError, match="line 2.*ceiling"):
        parse("# x\nplugin-hostd-protocol >= 0.7.0 < 0.8\n")


def test_the_repository_declares_floors_only():
    """contract-versions itself: every line a floor, none with a ceiling, and the estimate reply's floor: the
    10-word form (the four RAM words) is the only one python3-plugin-hostd-protocol 0.7.0 reads."""
    with open(os.path.join(ROOT, "contract-versions")) as f:
        floors = parse(f.read())
    assert floors["plugin-hostd-protocol"] == "0.7.0"
    assert floors["python3-plugin-hostd-protocol"] == "0.7.0"


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
    import re

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
