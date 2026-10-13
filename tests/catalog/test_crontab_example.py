"""
S8 (decision 8.144 h): the production crontab writes one dated log a day per
job, deletes logs after 14 days, keeps its heavy lock out of /tmp, and the
deploy gate writes a dated log too.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRONTAB = (ROOT / 'uberspaceconfig/crontab/crontab.example').read_text(
    encoding='utf-8')
GATE = (ROOT / 'uberspaceconfig/deployment/csc_deploy_gate.sh').read_text(
    encoding='utf-8')
JOBS = [line for line in CRONTAB.splitlines()
        if line and not line.startswith('#') and '=' not in line.split()[0]]


def test_there_are_five_jobs_and_a_retention_line():
    assert len(JOBS) == 6
    assert sum('find ' in line for line in JOBS) == 1


def test_every_job_appends_to_a_log_of_the_day_with_the_percent_escaped():
    for line in JOBS:
        if 'find ' in line:
            continue
        match = re.search(r'>> (.+?) 2>&1$', line)
        assert match, line
        target = match.group(1)
        assert re.fullmatch(
            r'/home/ddu/csc/shared/logs/[a-z_]+_cronjob\.\$\(date \+\\%F\)\.log',
            target), target


def test_no_percent_is_left_unescaped():
    for line in JOBS:
        assert not re.search(r'(?<!\\)%', line), line


def test_one_line_deletes_the_cron_and_deploy_logs_after_14_days():
    (retention,) = [line for line in JOBS if 'find ' in line]
    assert '/home/ddu/csc/shared/logs' in retention
    assert "-name '*_cronjob.*.log'" in retention
    assert "-name 'deploy.*.log'" in retention
    assert '-mtime +14' in retention and retention.rstrip().endswith('-delete')


def test_the_heavy_lock_is_not_in_tmp():
    assert not any('/tmp' in line for line in JOBS)
    assert sum('/home/ddu/csc/shared/locks/heavy.lock' in line for line in JOBS) == 3


def test_the_deploy_gate_writes_a_log_of_the_day():
    assert 'deploy.$(date +%F).log' in GATE
    assert 'deploy.log"' not in GATE
