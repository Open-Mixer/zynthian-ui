# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Engine (zynthian_release_target)
#
# The release tag update_zynthian.sh would take for a repository
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# ******************************************************************************
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the LICENSE.txt file.
#
# ******************************************************************************

import os
import logging
from subprocess import check_output, run, PIPE, STDOUT


def get_repo_branch(path):
    res = check_output(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
                       encoding="utf-8", stderr=STDOUT).strip()
    parts = res.split("/", 1)
    if len(parts) > 1 and parts[0] == 'heads':
        return parts[1]
    return res


def release_target(path, stable_branch, sys_dir=None):
    """The release tag the updater would move the repository at path to, or None

    zynthian-sys names it when it has scripts/omx-release-target.sh: the newest
    tag that contains what the device runs. Without that script it is the last
    tag listed, as upstream has it.
    """

    if sys_dir is None:
        sys_dir = os.environ.get('ZYNTHIAN_SYS_DIR', "/zynthian/zynthian-sys")
    script = os.path.join(sys_dir, "scripts", "omx-release-target.sh")
    if os.access(script, os.X_OK):
        res = run([script, "--fetch", path, stable_branch], stdout=PIPE, stderr=PIPE, encoding="utf-8")
        for line in res.stderr.splitlines():
            logging.debug(line)
        tag = res.stdout.strip()
        if res.returncode == 0 and tag:
            return tag
        return None
    stags = check_output(["git", "-C", path, "tag", "-l", f"{stable_branch}-*"],
                         encoding="utf-8", stderr=STDOUT).strip().split("\n")
    return stags[-1].strip() or None


def update_available(path, stable_branch, sys_dir=None):
    """True when the updater would move the repository at path to another release tag"""

    target = release_target(path, stable_branch, sys_dir)
    return target is not None and target != get_repo_branch(path)
