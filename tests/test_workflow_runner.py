# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The pytest job runs on the arm64 cell: the OpenMixer debs this suite installs (plugin-hostd and its contract, the
python readers) are arm64-only for trixie, and an amd64 container can never install them (the served_pair red, waiver (b),
zynthian-ui#94). The job's runner is the arm64 runner and its name says the architecture; the arm: a tree whose job
runs on ubuntu-latest is read as a fault."""
import pathlib
import unittest

import yaml

WORKFLOW = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows" / "tests.yml"
ARM = "ubuntu-24.04-arm"


def faults(doc):
    out = []
    for name, job in (doc.get("jobs") or {}).items():
        if "pytest" not in str(job.get("name", "")) and "pytest" not in str(job.get("steps", "")):
            continue
        runs = str(job.get("runs-on"))
        if runs != ARM:
            out.append(f"job {name}: runs-on is {runs!r}, not {ARM!r}")
        if "arm64" not in str(job.get("name", "")):
            out.append(f"job {name}: its name does not say arm64")
    return out


class WorkflowRunner(unittest.TestCase):
    def test_the_pytest_job_runs_on_the_arm64_cell(self):
        doc = yaml.safe_load(WORKFLOW.read_text())
        self.assertTrue(any("pytest" in str(j.get("name", "")) for j in doc["jobs"].values()), "no pytest job found")
        self.assertEqual(faults(doc), [])

    def test_arm_a_job_on_ubuntu_latest_is_a_fault(self):
        doc = {"jobs": {"tests": {"name": "python3 -m pytest tests/ (debian:trixie arm64)", "runs-on": "ubuntu-latest"}}}
        self.assertEqual(len(faults(doc)), 1)
        doc = {"jobs": {"tests": {"name": "python3 -m pytest tests/ (debian:trixie)", "runs-on": ARM}}}
        self.assertEqual(len(faults(doc)), 1)


if __name__ == "__main__":
    unittest.main()
