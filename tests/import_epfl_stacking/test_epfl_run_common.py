"""run.py against a fake API, and the dataset folder helpers (decision 8.146)."""

from __future__ import annotations

import json

import pytest

from test_epfl_plan import meta_of


class FakeApi:
    """Answers the calls of ``run_item`` for a stone that exists in a chosen state; remembers every call."""

    def __init__(self, status='published', resolutions=None, exists=True, cloud='inline', cloud_size=0):
        self.status, self.resolutions, self.exists = status, resolutions or {}, exists
        self.cloud, self.cloud_size = cloud, cloud_size            # what GET .../point_clouds/0.ply serves
        self.calls, self.bodies, self.streamed, self.read, self.closed = [], [], [], [], []

    def request(self, method, path, **kw):
        self.calls.append((method, path))
        if path.endswith('/point_clouds/0.ply'):
            return self._cloud_response(path, kw)
        found = 200 if self.exists else 404

        class Found:
            status_code = found
        return Found()

    def _cloud_response(self, path, kw):
        api = self
        self.streamed.append(bool(kw.get('stream')))
        file = {'Cache-Control': 'private, max-age=86400', 'Content-Length': str(self.cloud_size)}
        inline = {'Cache-Control': 'private, max-age=3600', 'Content-Length': '69137'}

        class Cloud:
            status_code = 404 if api.cloud == 'none' else 200
            headers = file if api.cloud == 'file' else inline
            content = property(lambda self: api.read.append(path) or b'the whole file')   # a download

            def close(self):
                api.closed.append(path)
        return Cloud()

    def json(self, method, path, ok=(200, 201), **kw):
        self.calls.append((method, path))
        self.bodies.append((method, path, kw))
        if path.endswith('/compose?snapshots=all'):
            return {'snapshots': [{'_id': 'SNAP-1'}]}
        if method == 'POST' and path == '/identities':
            return {'snapshot': {'_id': 'SNAP-1'}}
        if path == '/snapshots/SNAP-1':
            return {'status': self.status, 'mesh_ply_resolutions': self.resolutions}
        return None


def one_item(plan_module, tmp_path):
    item = plan_module.item(meta_of())
    folder = tmp_path / 'stones' / 'A0'
    folder.mkdir(parents=True)
    (folder / 'preview.json').write_text(json.dumps({
        'mesh': {'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0]], 'faces': [[0, 1, 2]]},
        'cloud': {'points': [[0, 0, 0]], 'colors': [[1, 2, 3]]}}), encoding='utf-8')
    for name in ('reduced.ply', 'detailed.ply', 'cloud.ply'):
        (folder / name).write_bytes(b'ply\n' + name.encode())
    return item


@pytest.fixture
def run_module(script_loader):
    pytest.importorskip('requests')
    return script_loader('run')


def stats():
    return dict(identities=0, existing=0, published=0, ply=0, clouds=0)


def test_a_new_stone_is_created_uploaded_submitted_and_published(run_module, plan_module, tmp_path):
    item = one_item(plan_module, tmp_path)
    api, counts = FakeApi(exists=False, status='draft'), stats()
    run_module.run_item(api, tmp_path, item, counts, lambda _m: None)
    methods = [(m, p) for m, p in api.calls if m != 'GET']
    assert methods == [('POST', '/identities'),
                       ('PUT', '/snapshots/SNAP-1/meshes/0/reduced'),
                       ('PUT', '/snapshots/SNAP-1/meshes/0/detailed'),
                       ('PUT', '/snapshots/SNAP-1/point_clouds/0.ply'),
                       ('POST', '/snapshots/SNAP-1/submit'),
                       ('POST', '/snapshots/SNAP-1/publish?promote=1')]
    assert counts == dict(identities=1, existing=0, published=1, ply=2, clouds=1)
    created = api.bodies[0][2]['json']
    assert created['snapshot']['geometry']['meshes'][0]['faces'] == [[0, 1, 2]]
    assert created['snapshot']['geometry']['point_clouds'][0]['points'] == [[0, 0, 0]]


def test_a_published_stone_is_left_alone(run_module, plan_module, tmp_path):
    item = one_item(plan_module, tmp_path)
    api, counts = FakeApi(status='published'), stats()
    run_module.run_item(api, tmp_path, item, counts, lambda _m: None)
    assert [(m, p) for m, p in api.calls if m != 'GET'] == []
    assert counts['existing'] == 1 and counts['identities'] == 0 and counts['published'] == 0


def test_a_draft_that_stopped_midway_sends_only_what_is_missing(run_module, plan_module, tmp_path):
    item = one_item(plan_module, tmp_path)
    api = FakeApi(status='draft', resolutions={'0': ['reduced']})
    run_module.run_item(api, tmp_path, item, stats(), lambda _m: None)
    puts = [p for m, p in api.calls if m == 'PUT']
    assert puts == ['/snapshots/SNAP-1/meshes/0/detailed', '/snapshots/SNAP-1/point_clouds/0.ply']
    assert ('POST', '/snapshots/SNAP-1/publish?promote=1') in api.calls


def test_a_cloud_the_snapshot_already_has_is_not_sent_again(run_module, plan_module, tmp_path):
    item = one_item(plan_module, tmp_path)
    size = (tmp_path / item['files']['cloud']).stat().st_size
    api, counts = FakeApi(status='draft', cloud='file', cloud_size=size), stats()
    run_module.run_item(api, tmp_path, item, counts, lambda _m: None)
    puts = [p for m, p in api.calls if m == 'PUT']
    assert '/snapshots/SNAP-1/point_clouds/0.ply' not in puts
    assert puts == ['/snapshots/SNAP-1/meshes/0/reduced', '/snapshots/SNAP-1/meshes/0/detailed']
    assert counts['clouds'] == 0 and counts['published'] == 1
    assert api.streamed == [True] and api.read == [] and len(api.closed) == 1      # headers only, closed


@pytest.mark.parametrize('cloud, size_delta', [('inline', 0), ('none', 0), ('file', 1)])
def test_a_cloud_that_is_not_there_or_not_whole_is_sent(run_module, plan_module, tmp_path, cloud, size_delta):
    """The inline fallback of the API, no cloud, or a file of another size (a cut-off upload): sent."""
    item = one_item(plan_module, tmp_path)
    size = (tmp_path / item['files']['cloud']).stat().st_size
    api, counts = FakeApi(status='draft', cloud=cloud, cloud_size=size + size_delta), stats()
    run_module.run_item(api, tmp_path, item, counts, lambda _m: None)
    assert ('PUT', '/snapshots/SNAP-1/point_clouds/0.ply') in api.calls and counts['clouds'] == 1
    assert api.read == []                                                          # never downloaded


def test_a_stone_without_a_staged_cloud_never_asks_for_one(run_module, plan_module, tmp_path):
    item = plan_module.item(meta_of(staged=False))
    one_item(plan_module, tmp_path)
    api = FakeApi(status='draft')
    run_module.run_item(api, tmp_path, item, stats(), lambda _m: None)
    assert not any(p.endswith('/point_clouds/0.ply') for _, p in api.calls)


def test_a_pending_stone_is_only_published(run_module, plan_module, tmp_path):
    api = FakeApi(status='pending')
    run_module.run_item(api, tmp_path, one_item(plan_module, tmp_path), stats(), lambda _m: None)
    assert [(m, p) for m, p in api.calls if m != 'GET'] == [('POST', '/snapshots/SNAP-1/publish?promote=1')]


@pytest.mark.parametrize('state', ['rejected', 'withdrawn'])
def test_a_rejected_or_withdrawn_snapshot_is_logged_with_state_and_id(run_module, plan_module, tmp_path, state):
    lines = []
    api = FakeApi(status=state)
    run_module.run_item(api, tmp_path, one_item(plan_module, tmp_path), stats(), lines.append)
    assert 'epfl_stacking:A0: snapshot SNAP-1 is ' + state in lines
    if state == 'withdrawn':
        assert [(m, p) for m, p in api.calls if m != 'GET'] == []          # left alone, only said


# THE DATASET FOLDER -----------------------------------------------------------------------------------
def test_find_root_takes_the_folder_with_stones_in_any_of_the_places(epfl, tmp_path):
    (tmp_path / 'a' / 'stones').mkdir(parents=True)
    assert epfl.find_root(tmp_path / 'a') == tmp_path / 'a'
    (tmp_path / 'b' / 'unpacked' / 'repo-123' / 'stones').mkdir(parents=True)
    assert epfl.find_root(tmp_path / 'b') == tmp_path / 'b' / 'unpacked' / 'repo-123'
    (tmp_path / 'c' / 'repo-9' / 'stones').mkdir(parents=True)
    assert epfl.find_root(tmp_path / 'c') == tmp_path / 'c' / 'repo-9'
    with pytest.raises(FileNotFoundError, match='run fetch.py first'):
        epfl.find_root(tmp_path / 'nothing')


def test_stones_are_listed_by_group_and_number_and_a_lone_file_is_an_error(epfl, tmp_path):
    meshes, clouds = tmp_path / 'stones' / 'mesh_high_res', tmp_path / 'stones' / 'pcd_high_res'
    meshes.mkdir(parents=True)
    clouds.mkdir(parents=True)
    for sid in ('A10', 'A2', 'B1'):
        (meshes / f'remeshed_high_res_{sid}.ply').write_text('x')
        (clouds / f'pcd_high_res_{sid}.ply').write_text('x')
    (meshes / 'notes.txt').write_text('x')
    assert list(epfl.stone_files(tmp_path)) == ['A2', 'A10', 'B1']                 # numeric, not alphabetic
    (clouds / 'pcd_high_res_B1.ply').unlink()
    with pytest.raises(ValueError, match='B1'):
        epfl.stone_files(tmp_path)
