"""The test harness opens a JACK client before it starts jackd (tests/jacktest.py).

libjack's metadata store is a Berkeley DB environment shared by every JACK process (/dev/shm/jack_db-<uid>),
created by the first process that opens it. Where it does not exist yet, jackd and the harness's first probe
would create it at once and one waits for the other (a 3 s stall on a fresh CI runner). A client opened before
jackd starts creates it from the test process alone.

libjack and jackd are faked here: what is checked is the order of the calls, never a real server.
"""

import pytest

jacktest = pytest.importorskip("tests.jacktest")


class FakeProc:
    def __init__(self, calls):
        self.calls = calls

    def poll(self):
        return None

    def terminate(self):
        self.calls.append("terminate")

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def calls(monkeypatch):
    calls = []
    answers = {"up": False}

    class FakeClient:
        def __init__(self, name, servername=None, no_start_server=False):
            assert no_start_server, "the harness must never let libjack start a server"
            calls.append("client")
            if not answers["up"]:
                raise jacktest.jack.JackError("<jack.Status 0x11: failure, server_failed>")

        def close(self):
            pass

    def fake_popen(argv, **kwargs):
        assert argv[0] == "jackd"
        calls.append("jackd")
        answers["up"] = True
        return FakeProc(calls)

    monkeypatch.setattr(jacktest.jack, "Client", FakeClient)
    monkeypatch.setattr(jacktest.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(jacktest, "reclaim_dead_test_servers", lambda: [])
    monkeypatch.setattr(jacktest, "reclaim_orphan_metadata_env", lambda: calls.append("reclaim") and False)
    monkeypatch.delenv("JACK_DEFAULT_SERVER", raising=False)
    return calls


def test_a_client_is_opened_before_jackd_starts_so_one_process_creates_the_metadata_environment(calls):
    jacktest.JackTestServer("zyntest_order").start()
    assert calls[:3] == ["reclaim", "client", "jackd"], calls
    assert calls[-1] == "client"  # the probe that found the server up


def test_a_server_that_never_answers_is_reported_with_what_jackd_said(calls, monkeypatch):
    def popen_silent_server(argv, stdout=None, **kwargs):
        calls.append("jackd")
        stdout.write(b"BDB1546 unable to join the environment\n")
        stdout.flush()
        return FakeProc(calls)

    monkeypatch.setattr(jacktest.subprocess, "Popen", popen_silent_server)
    monkeypatch.setattr(jacktest.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as e:
        jacktest.JackTestServer("zyntest_silent").start(timeout=0)
    assert "BDB1546 unable to join the environment" in str(e.value)
    assert "still running at the timeout" in str(e.value)
    assert calls[:3] == ["reclaim", "client", "jackd"]
