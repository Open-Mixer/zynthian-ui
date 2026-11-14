"""tools/contract_versions.py: the contract versions the series is built and tested against, declared once in
contract-versions (`<package> >= <floor> < <ceiling>` per line), and the check that what is installed is inside them.
An installed version below its floor (the series cut against an older contract) or at its ceiling is named, never
read as a failing test."""
import pytest

from tools.contract_versions import parse, check, packages as packages_of

DECLARED = """# the contract the series is built and tested against
plugin-hostd-protocol >= 0.5.8 < 0.6
plugin-hostd-contract >= 0.20.4 < 0.21
"""


def test_the_declaration_parses_into_ranges():
    assert parse(DECLARED) == {"plugin-hostd-protocol": ("0.5.8", "0.6"), "plugin-hostd-contract": ("0.20.4", "0.21")}


def test_an_installed_set_inside_the_ranges_is_clean():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.5.8-1", "plugin-hostd-contract": "0.20.4-1"}) == []


def test_below_the_floor_is_named():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.5.5-1", "plugin-hostd-contract": "0.20.4"}) == [
        "plugin-hostd-protocol 0.5.5-1 is below the declared floor 0.5.8"]


def test_at_the_ceiling_is_named():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.6.0", "plugin-hostd-contract": "0.20.10"}) == [
        "plugin-hostd-protocol 0.6.0 is at or above the declared ceiling 0.6"]


def test_a_declared_package_not_installed_is_named():
    assert check(parse(DECLARED), {"plugin-hostd-protocol": "0.5.8"}) == ["plugin-hostd-contract is not installed"]


def test_a_line_that_is_not_a_range_is_an_error():
    with pytest.raises(ValueError, match="line 2"):
        parse("# x\nplugin-hostd-protocol 0.5.8\n")


def test_omx_contract_readers_are_imported_from_python3_omx_contract():
    """The position law and the catalog reader are omx-contract's package omx_contract (python3-omx-contract,
    omx-contract#28): imported as omx_contract.scale and omx_contract.catalog, never as a file found under
    /usr/share/omx-contract, and the package that carries them is declared in contract-versions."""
    import os
    import re

    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
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
