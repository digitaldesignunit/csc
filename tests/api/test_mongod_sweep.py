"""Leftover temporary folders of killed runs are swept; live ones stay."""

import os
import tempfile
import time

from mongod import pid_alive, sweep_stale_dirs


def _folder(prefix, pid, age_s):
    path = tempfile.mkdtemp(prefix=prefix)
    with open(os.path.join(path, 'owner.pid'), 'w', encoding='ascii') as handle:
        handle.write(str(pid))
    past = time.time() - age_s
    os.utime(path, (past, past))
    return path


def test_sweep_removes_only_dead_old_folders():
    prefix = 'csc-sweeptest-'
    dead = _folder(prefix, 2_147_000_000, age_s=3600)
    alive = _folder(prefix, os.getpid(), age_s=3600)
    young = _folder(prefix, 2_147_000_000, age_s=0)
    try:
        assert pid_alive(os.getpid()) and not pid_alive(2_147_000_000)
        assert sweep_stale_dirs(prefix) == 1
        assert not os.path.exists(dead)
        assert os.path.isdir(alive) and os.path.isdir(young)
    finally:
        for path in (dead, alive, young):
            if os.path.isdir(path):
                for name in os.listdir(path):
                    os.remove(os.path.join(path, name))
                os.rmdir(path)
