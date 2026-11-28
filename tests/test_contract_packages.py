"""tools/contract_packages.py: the contract packages the series is built and tested against, declared once in
contract-packages (`<package> [<path>...]` per line), and the check that each is installed and lays down what the code
reads. No floor is typed: the next level uses the published package, and the run records the version it found. The
hand-kept floors this replaced (omx-contract-data >= 3.14.0, omx-contract >= 3.18.1) could never pass once the
packages were numbered 0.M.m (run 45944586295: "omx-contract-data 0.23.4 is not >= 3.14.0")."""
import ast
import os

import pytest

from tools.contract_packages import parse, check

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

DECLARED = """# the contract the series is built and tested against
omx-contract-data /usr/share/omx-contract/contract.d/omx-contract/MANIFEST.json
python3-plugin-hostd-protocol
"""
MANIFEST = "/usr/share/omx-contract/contract.d/omx-contract/MANIFEST.json"


def declared_here():
    with open(os.path.join(ROOT, "contract-packages")) as f:
        return parse(f.read())


def test_the_declaration_parses_into_packages_and_paths():
    assert parse(DECLARED) == {"omx-contract-data": [MANIFEST], "python3-plugin-hostd-protocol": []}


def test_a_0_M_m_release_is_clean():
    """The red of run 45944586295: 0.23.4 read below a floor of 3.14.0. Whatever the number, an installed package
    that lays down its domain is the series' contract."""
    installed = {"omx-contract-data": "0.23.4", "python3-plugin-hostd-protocol": "0.21.4"}
    owned = {"omx-contract-data": {MANIFEST}}
    assert check(parse(DECLARED), installed, owned, lambda p: True) == []


def test_a_package_not_installed_is_named():
    assert check(parse(DECLARED), {"omx-contract-data": "0.23.4"}, {"omx-contract-data": {MANIFEST}},
                 lambda p: True) == ["python3-plugin-hostd-protocol is not installed"]


def test_a_domain_missing_is_named():
    installed = {"omx-contract-data": "0.23.4", "python3-plugin-hostd-protocol": "0.21.4"}
    assert check(parse(DECLARED), installed, {"omx-contract-data": {MANIFEST}}, lambda p: False) == [
        f"omx-contract-data 0.23.4: {MANIFEST} is missing"]


def test_a_path_another_package_lays_down_is_named():
    installed = {"omx-contract-data": "0.23.4", "python3-plugin-hostd-protocol": "0.21.4"}
    assert check(parse(DECLARED), installed, {"omx-contract-data": set()}, lambda p: True) == [
        f"omx-contract-data 0.23.4: {MANIFEST} is not laid down by omx-contract-data"]


@pytest.mark.parametrize("line", ["omx-contract-data >= 3.14.0", "omx-contract-data (>= 0.23.4)",
                                  "omx-contract-data < 1.0", "omx-contract-data = 0.23.4",
                                  "omx-contract-data 0.23.4"])
def test_a_typed_floor_is_refused(line):
    """A version on a line is a floor kept by hand: refused, naming the line."""
    with pytest.raises(ValueError, match="line 2.*(version|floor)"):
        parse("# x\n" + line + "\n")


def test_a_path_that_is_not_absolute_is_refused():
    with pytest.raises(ValueError, match="line 1.*absolute"):
        parse("omx-contract-data contract.d/omx-contract\n")


def test_a_package_declared_twice_is_refused():
    with pytest.raises(ValueError, match="line 2.*second time"):
        parse("omx-contract-data\nomx-contract-data /usr/share/omx-contract\n")


def test_the_repository_types_no_floor():
    """contract-packages itself parses (no version anywhere), and declares the domains the code reads: omx-contract's
    vocabularies, the protocol's documents and the daemon's grouping reasons."""
    d = declared_here()
    assert MANIFEST in d["omx-contract-data"]
    assert "/usr/share/plugin-hostd-protocol/plugin-hostd.json" in d["libplugin-hostd-protocol0"]
    assert "/usr/share/omx-contract/contract.d/plugin-hostd/grouping/grouping.json" in d["plugin-hostd-contract"]


def test_no_workflow_compares_a_version_by_hand():
    """The CI's floor lived in the workflow too (dpkg --compare-versions ... ge 3.14.0): no workflow of this
    repository compares an installed version against a typed one."""
    import re
    wf = os.path.join(ROOT, ".github", "workflows")
    found = []
    for name in sorted(os.listdir(wf)):
        with open(os.path.join(wf, name)) as f:
            for n, line in enumerate(f, 1):
                if re.search(r"compare-versions|--atleast-version|\bge\s+\d+\.\d+", line):
                    found.append(f"{name}:{n}: {line.strip()}")
    assert found == []


def test_the_client_the_runtime_imports_is_declared_and_carries_every_name():
    """zyngine/zynthian_plugin_hostd_protocol.py imports plugin-hostd's Python client at module load: the package that
    carries it (python3-plugin-hostd-protocol) is declared in contract-packages, and the installed client exports
    every name imported from it."""
    import plugin_hostd_protocol

    assert "python3-plugin-hostd-protocol" in declared_here()
    with open(os.path.join(ROOT, "zyngine", "zynthian_plugin_hostd_protocol.py")) as f:
        tree = ast.parse(f.read())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "plugin_hostd_protocol"
                for a in n.names}
    assert imported
    assert sorted(imported - set(plugin_hostd_protocol.__all__)) == []


def test_omx_contract_readers_are_imported_from_python3_omx_contract():
    """The position law and the catalog reader are omx-contract's package omx_contract (python3-omx-contract,
    omx-contract#28): imported as omx_contract.scale and omx_contract.catalog, never as a file found under
    /usr/share/omx-contract, and the package that carries them is declared in contract-packages."""
    import re

    assert "python3-omx-contract" in declared_here()
    by_path = re.compile(r"^\s*(?:import|from)\s+(omx_contract_(?:scale|catalog))\b", re.M)
    found = []
    for d in ("zyngine", "zyngui", "tests"):
        for dirpath, _, files in os.walk(os.path.join(ROOT, d)):
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(dirpath, name)
                    with open(path, encoding="utf-8", errors="replace") as f:
                        found += [f"{os.path.relpath(path, ROOT)}: {m}" for m in by_path.findall(f.read())]
    assert found == []
