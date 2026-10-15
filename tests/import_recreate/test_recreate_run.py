"""run.py: what one item does against an instance that already holds it, from a fake API (no server)."""

from __future__ import annotations

import pytest

import recreate_samples as s


class FakeApi:
    """Answers the calls of ``run_item`` for an identity that exists with one snapshot and a few evidence
    records; remembers every call."""

    def __init__(self, snapshot_status='published', records=()):
        self.snapshot_status, self.records, self.calls = snapshot_status, list(records), []

    def request(self, method, path, **kw):
        self.calls.append((method, path))

        class Found:
            status_code = 200
        return Found()

    def json(self, method, path, ok=(200, 201), **kw):
        self.calls.append((method, path))
        if path.endswith('/compose?snapshots=all'):
            return {'snapshots': [{'_id': 'SNAP-1'}]}
        if path == '/snapshots/SNAP-1':
            return {'status': self.snapshot_status, 'mesh_ply_resolutions': {'0': ['detailed']}}
        if '/evidence?' in path:
            return self.records
        if path == '/evidence/bulk':
            return {'records': []}
        return None


@pytest.fixture
def run_module(script_loader):
    pytest.importorskip('numpy')
    pytest.importorskip('requests')
    return script_loader('run')


def one_item(plan_module, tmp_path):
    parsed, geometry = s.parsed_and_geometry()
    planner = plan_module.Planner(parsed, geometry)
    planner.run()
    item = planner.items[0]
    s.write_box(tmp_path / item['mesh_ply'])
    return item


def stats():
    return dict(identities=0, existing=0, published=0, ply=0, evidence=0)


def record(status, ref='some-other-reference'):
    return {'_id': f'EV-{status}', 'status': status, 'payload': {'document': {'reference': ref}}}


@pytest.mark.parametrize('state', ['rejected', 'withdrawn'])
def test_a_snapshot_found_rejected_or_withdrawn_is_logged_with_its_state_and_id(
        run_module, plan_module, tmp_path, state):
    item, lines = one_item(plan_module, tmp_path), []
    api = FakeApi(snapshot_status=state)
    run_module.run_item(api, tmp_path, item, stats(), lines.append)
    assert f'{item["key"]}: snapshot SNAP-1 is {state}' in lines


def test_a_rejected_snapshot_is_still_resubmitted_as_before(run_module, plan_module, tmp_path):
    """The log line changes nothing: a rejected snapshot goes the way it always went, a withdrawn one
    is left alone."""
    item = one_item(plan_module, tmp_path)
    rejected = FakeApi(snapshot_status='rejected')
    run_module.run_item(rejected, tmp_path, item, stats(), lambda _m: None)
    assert ('POST', '/snapshots/SNAP-1/submit') in rejected.calls
    assert ('POST', '/snapshots/SNAP-1/publish?promote=1') in rejected.calls
    withdrawn = FakeApi(snapshot_status='withdrawn')
    run_module.run_item(withdrawn, tmp_path, item, stats(), lambda _m: None)
    assert not any(path.endswith('/submit') or 'publish' in path for _, path in withdrawn.calls
                   if _ == 'POST')


def test_a_published_snapshot_logs_nothing(run_module, plan_module, tmp_path):
    item, lines = one_item(plan_module, tmp_path), []
    run_module.run_item(FakeApi(), tmp_path, item, stats(), lines.append)
    assert lines == []


@pytest.mark.parametrize('state', ['rejected', 'withdrawn'])
def test_an_evidence_record_found_rejected_or_withdrawn_is_logged_with_its_state_and_id(
        run_module, plan_module, tmp_path, state):
    item, lines = one_item(plan_module, tmp_path), []
    api = FakeApi(records=[record(state), record('published', ref='another')])
    run_module.run_item(api, tmp_path, item, stats(), lines.append)
    assert f'{item["key"]}: evidence record EV-{state} is {state}' in lines
    assert not any('EV-published' in line for line in lines)
    # nothing is published or submitted for it: the behaviour is the one it was
    assert ('POST', f'/evidence/EV-{state}/publish') not in api.calls
    assert ('POST', f'/evidence/EV-{state}/submit') not in api.calls
