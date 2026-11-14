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


def test_the_client_the_runtime_imports_is_declared_and_carries_every_name():
    """zyngine/zynthian_plugin_hostd_protocol.py imports plugin-hostd's Python client at module load: the package that
    carries it (python3-plugin-hostd-protocol) is declared in contract-versions, and the installed client exports
    every name imported from it."""
    import ast
    import os
    import plugin_hostd_protocol

    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    with open(os.path.join(root, "contract-versions")) as f:
        assert "python3-plugin-hostd-protocol" in packages_of(f.read())
    with open(os.path.join(root, "zyngine", "zynthian_plugin_hostd_protocol.py")) as f:
        tree = ast.parse(f.read())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "plugin_hostd_protocol"
                for a in n.names}
    assert imported
    assert sorted(imported - set(plugin_hostd_protocol.__all__)) == []
