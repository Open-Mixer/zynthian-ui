"""The test harness removes a JACK metadata environment that no process holds (tests/jacktest.py).

libjack's metadata store is a Berkeley DB environment, /dev/shm/jack_db-<uid>, created by the first JACK process
that opens it. A process killed while creating it (the hermetic ctrldev tests terminate a driver's MIDI process as
it starts) leaves an empty __db.001 nobody can join, and then every native test errored: "BDB1546 unable to join
the environment", "Can't start jackd server". An environment no process holds is garbage, and removed; one that a
process maps or holds open is never touched.

These tests work on a fake /dev/shm and a fake /proc, never on the real ones.
"""

import os

import pytest

jacktest = pytest.importorskip("tests.jacktest")


@pytest.fixture
def shm(tmp_path):
    (tmp_path / "shm").mkdir()
    (tmp_path / "proc").mkdir()
    return tmp_path


def make_env(shm, files=("__db.001",)):
    env = shm / "shm" / f"jack_db-{os.getuid()}"
    env.mkdir()
    for name in files:
        (env / name).write_bytes(b"")
    return env


def make_process(shm, pid, maps="", fds=()):
    proc = shm / "proc" / str(pid)
    (proc / "fd").mkdir(parents=True)
    (proc / "maps").write_text(maps)
    for i, target in enumerate(fds):
        os.symlink(target, proc / "fd" / str(i))


def reclaim(shm):
    return jacktest.reclaim_orphan_metadata_env(shm_dir=str(shm / "shm"), proc=str(shm / "proc"))


def test_an_environment_no_process_holds_is_removed(shm):
    env = make_env(shm)
    make_process(shm, 100, maps="7f00-7f10 r-xp 00000000 08:01 1 /usr/lib/libjack.so.0\n", fds=["/dev/null"])
    assert reclaim(shm) is True
    assert not env.exists()


def test_an_environment_a_process_maps_is_kept(shm):
    env = make_env(shm, ("__db.001", "__db.002", "metadata.db"))
    make_process(shm, 100, maps=f"7f00-7f10 rw-s 00000000 00:19 7 {env}/__db.001\n")
    assert reclaim(shm) is False
    assert sorted(p.name for p in env.iterdir()) == ["__db.001", "__db.002", "metadata.db"]


def test_an_environment_a_process_holds_open_is_kept(shm):
    env = make_env(shm)
    make_process(shm, 100, fds=["/dev/null", f"{env}/__db.001"])
    assert reclaim(shm) is False
    assert (env / "__db.001").exists()


def test_no_environment_is_nothing_to_do(shm):
    make_process(shm, 100)
    assert reclaim(shm) is False
