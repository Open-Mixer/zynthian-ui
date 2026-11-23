"""tools/served_pair.py: the newest version a set of packages is served at TOGETHER in one channel cell, read from the
channel's deb/cells.tsv (the file served.sh reads). The CI installs plugin-hostd and its contract at that version, so
a release that has reached only some cells (plugin-hostd 0.20.5 and 0.20.6 on arm64 alone, their contract everywhere)
never reads as this repository's red: amd64 tests against the newest pair amd64 has."""
import pytest

from tools.served_pair import served_pair

CELLS = """# package\tversion\tset\tcells
plugin-hostd\t0.20.4\t-\tbookworm/amd64 bookworm/arm64 trixie/amd64
plugin-hostd\t0.20.5\tquick\ttrixie/arm64
plugin-hostd\t0.20.6\tquick\ttrixie/arm64
plugin-hostd-contract\t0.20.4\t-\tbookworm/all trixie/all
plugin-hostd-contract\t0.20.5\tquick\ttrixie/all
plugin-hostd-contract\t0.20.6\tquick\ttrixie/all
"""
PAIR = ["plugin-hostd", "plugin-hostd-contract"]


def test_a_cell_the_release_has_not_reached_takes_the_newest_pair_it_has():
    assert served_pair(CELLS, "trixie/amd64", PAIR) == "0.20.4"


def test_a_cell_the_release_reached_takes_the_release():
    assert served_pair(CELLS, "trixie/arm64", PAIR) == "0.20.6"


def test_once_the_release_reaches_every_cell_it_is_the_pair():
    whole = CELLS + "plugin-hostd\t0.20.7\tquick\ttrixie/amd64 trixie/arm64\nplugin-hostd-contract\t0.20.7\tquick\ttrixie/all\n"
    assert served_pair(whole, "trixie/amd64", PAIR) == "0.20.7"


def test_versions_compare_as_versions_not_text():
    cells = CELLS + "plugin-hostd\t0.20.10\t-\ttrixie/amd64\nplugin-hostd-contract\t0.20.10\t-\ttrixie/all\n"
    assert served_pair(cells, "trixie/amd64", PAIR) == "0.20.10"


def test_no_version_served_together_is_an_error_naming_the_cell():
    with pytest.raises(LookupError, match="trixie/amd64"):
        served_pair(CELLS, "trixie/amd64", ["plugin-hostd", "nosuch-package"])


def test_a_file_that_is_not_cells_tsv_is_an_error():
    with pytest.raises(ValueError, match="cells.tsv"):
        served_pair("<html>not found</html>", "trixie/amd64", PAIR)
