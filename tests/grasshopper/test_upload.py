"""The upload side of the Add components (csc_upload) against a fake
Session core: which requests it sends and how it reports the answers."""

from __future__ import annotations

import json

import pytest

from csc_gh import upload as up


class Response:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


class FakeCore:
    """The methods of the Session's ``_AuthCore`` the upload code uses."""

    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers or {}

    def _answer(self, method, path):
        for (m, p), response in self.answers.items():
            if m == method and path.startswith(p):
                return response
        return Response(200, {})

    def authorized_put(self, path, files=None, **kwargs):
        name, handle, media_type = next(iter(files.values()))
        self.calls.append(('PUT', path, next(iter(files)), name,
                           handle.read(), media_type, kwargs))
        return self._answer('PUT', path)

    def authorized_post(self, path, json_body=None, params=None, **kwargs):
        self.calls.append(('POST', path, json_body, params, kwargs))
        return self._answer('POST', path)

    def authorized_get(self, path, params=None, **kwargs):
        self.calls.append(('GET', path, params))
        return self._answer('GET', path)


def _stage(tmp_path):
    folder = tmp_path / 'abc'
    (folder / 'meshes' / '0').mkdir(parents=True)
    (folder / 'meshes' / '1').mkdir(parents=True)
    (folder / 'point_clouds').mkdir()
    (folder / 'meshes' / '0' / 'detailed.ply').write_bytes(b'ply-d0')
    (folder / 'meshes' / '0' / 'reduced.ply').write_bytes(b'ply-r0')
    (folder / 'meshes' / '1' / 'detailed.ply').write_bytes(b'ply-d1')
    (folder / 'point_clouds' / '0.ply').write_bytes(b'ply-c0')
    manifest = {'meshes': {'0': ['detailed', 'reduced'], '1': ['detailed']},
                'point_clouds': [0]}
    up.write_manifest(str(folder), manifest)
    return str(folder), manifest


def test_the_staged_plan_lists_files_and_what_is_missing(tmp_path):
    folder, manifest = _stage(tmp_path)
    assert up.load_manifest(folder) == manifest
    pending, missing = up.staged_plan(folder, manifest)
    assert [(e['kind'], e['index'], e['level']) for e in pending] == [
        ('mesh', 0, 'detailed'), ('mesh', 0, 'reduced'),
        ('mesh', 1, 'detailed'), ('point_cloud', 0, None)]
    assert missing == []
    (tmp_path / 'abc' / 'meshes' / '1' / 'detailed.ply').unlink()
    pending, missing = up.staged_plan(folder, manifest)
    assert len(pending) == 3 and missing[0]['index'] == 1
    assert up.load_manifest(str(tmp_path / 'nothing')) is None
    assert up.staged_plan(folder, None) == ([], [])


def test_the_files_go_to_the_servers_routes(tmp_path):
    folder, manifest = _stage(tmp_path)
    pending, _ = up.staged_plan(folder, manifest)
    core = FakeCore()
    told = []
    done, failed = up.upload_staged(core, 'sid', pending, told.append)
    assert len(done) == 4 and failed == []
    puts = [c for c in core.calls if c[0] == 'PUT']
    assert [(c[1], c[2], c[3], c[4]) for c in puts] == [
        ('/snapshots/sid/meshes/0/detailed', 'mesh_file', 'detailed.ply',
         b'ply-d0'),
        ('/snapshots/sid/meshes/0/reduced', 'mesh_file', 'reduced.ply',
         b'ply-r0'),
        ('/snapshots/sid/meshes/1/detailed', 'mesh_file', 'detailed.ply',
         b'ply-d1'),
        ('/snapshots/sid/point_clouds/0.ply', 'point_cloud_file', '0.ply',
         b'ply-c0')]
    assert all(c[5] == 'application/octet-stream' and c[6] == {'timeout': 300}
               for c in puts)
    assert len(told) == 4 and 'point cloud' in told[3]


def test_a_failed_upload_is_reported_and_the_rest_go_on(tmp_path):
    folder, manifest = _stage(tmp_path)
    pending, _ = up.staged_plan(folder, manifest)
    core = FakeCore({('PUT', '/snapshots/sid/meshes/0/reduced'): Response(
        400, {'detail': 'primitive_index 0 out of range'})})
    (tmp_path / 'abc' / 'meshes' / '1' / 'detailed.ply').unlink()
    done, failed = up.upload_staged(core, 'sid', pending)
    assert len(done) == 2 and len(failed) == 2
    reasons = [reason for _, reason in failed]
    assert 'primitive_index 0 out of range' in reasons[0]
    assert 'cannot read' in reasons[1]


def test_the_library_has_no_submit_path():
    """Grasshopper supplies drafts, submitting happens in the web (8.127)."""
    assert not hasattr(up, 'submit_snapshot')


def test_error_texts():
    assert 'HTTP 500' in up.http_error_text(Response(500, None), 'Create')
    text = up.http_error_text(Response(422, {'detail': [
        {'loc': ['body', 'snapshot', 'geometry'], 'msg': 'field required'},
        {'loc': ['body', 'dataset'], 'msg': 'unknown'}]}), 'Create')
    assert 'snapshot.geometry: field required' in text
    assert 'dataset: unknown' in text and text.startswith('Create failed')
    text = up.http_error_text(Response(422, {'detail': {
        'message': 'Not valid', 'errors': [
            {'path': 'records[0].payload.bars', 'message': 'needs a bar'}]}}),
        'Add evidence')
    assert 'Not valid' in text and 'records[0].payload.bars: needs a bar' \
        in text
    assert 'forbidden words' in up.http_error_text(
        Response(403, {'detail': 'forbidden words'}))
    fields = up.http_error_text(Response(422, {'detail': {
        'message': 'Server-maintained fields cannot be set.',
        'fields': ['frame', 'bbx']}}))
    assert 'frame' in fields and 'Server-maintained' in fields


def test_the_passport_after_a_create_is_the_servers_or_assembled():
    passport = {'identity': {'_id': 'i'}, 'snapshots': [{'_id': 's'}]}
    core = FakeCore({('GET', '/identities/i/compose'): Response(200, passport)})
    assert up.passport_after(core, {'_id': 'i'}, {'_id': 's'}) == passport
    assert core.calls[0] == ('GET', '/identities/i/compose',
                             {'snapshots': 's'})
    missing = FakeCore({('GET', '/identities/i'): Response(404, {})})
    assembled = up.passport_after(missing, {'_id': 'i', 'x': 1},
                                  {'_id': 's', 'status': 'draft'})
    assert assembled == {'identity': {'_id': 'i', 'x': 1},
                         'snapshots': [{'_id': 's', 'status': 'draft'}]}

    class Broken(FakeCore):
        def authorized_get(self, *a, **k):
            raise RuntimeError('offline')
    assert up.passport_after(Broken(), {'_id': 'i'}, {'_id': 's'})[
        'snapshots'] == [{'_id': 's'}]
    assert up.passport_after(FakeCore(), None, None) == {
        'identity': {}, 'snapshots': [{}]}


def test_commit_and_clear_staging(tmp_path):
    root = tmp_path / 'root'
    tmp = root / '_tmp_x'
    (tmp / 'meshes' / '0').mkdir(parents=True)
    (tmp / 'meshes' / '0' / 'detailed.ply').write_bytes(b'x')
    manifest = {'meshes': {'0': ['detailed']}}
    folder = up.commit_staging(str(tmp), 'key1', manifest, str(root))
    assert folder == str(root / 'key1') and not tmp.exists()
    assert up.load_manifest(folder) == manifest
    # a later create with the same key replaces the old files
    tmp2 = root / '_tmp_y'
    (tmp2 / 'meshes' / '0').mkdir(parents=True)
    (tmp2 / 'meshes' / '0' / 'reduced.ply').write_bytes(b'y')
    up.commit_staging(str(tmp2), 'key1', {'meshes': {'0': ['reduced']}},
                      str(root))
    assert not (root / 'key1' / 'meshes' / '0' / 'detailed.ply').exists()
    # nothing staged: the temporary folder goes, no folder is made
    tmp3 = root / '_tmp_z'
    tmp3.mkdir()
    assert up.commit_staging(str(tmp3), 'key2', {}, str(root)) is None
    assert not tmp3.exists() and not (root / 'key2').exists()
    assert up.clear_staging(str(root)) == str(root)
    assert list(root.iterdir()) == []


def test_the_staging_root_is_a_folder_of_ddu_csc():
    assert up.staging_root().endswith(
        ('DDU_CSC\\pending_assets', 'DDU_CSC/pending_assets'))
    assert up.staging_dir('k', 'r').endswith('k')


def test_a_manifest_cannot_steer_a_path_or_a_url(tmp_path):
    folder = tmp_path / 'abc'
    folder.mkdir()
    (tmp_path / 'secret.ply').write_bytes(b'ply')
    manifest = {'meshes': {'0': ['detailed', '../../secret', 'x/y'],
                           '../1': ['detailed'], 'two': ['reduced'],
                           '-3': ['reduced']},
                'point_clouds': [0, '../9', 'x', -1]}
    pending, missing = up.staged_plan(str(folder), manifest)
    assert pending == []                       # nothing exists, nothing odd
    kinds = [(m['kind'], str(m['index']), m['level']) for m in missing]
    assert ('mesh', '0', 'detailed') in kinds   # valid, but no file
    invalid = [m for m in missing if 'invalid manifest entry' in m['path']]
    assert len(invalid) == 8
    assert all('..' not in m['path'] or 'invalid' in m['path']
               for m in missing)
    # a valid file next to the odd entries is still uploaded, the odd ones not
    (folder / 'meshes' / '0').mkdir(parents=True)
    (folder / 'meshes' / '0' / 'detailed.ply').write_bytes(b'ply-d0')
    pending, _ = up.staged_plan(str(folder), manifest)
    assert [(e['index'], e['level']) for e in pending] == [(0, 'detailed')]
    assert up.upload_path('sid', pending[0]) ==         '/snapshots/sid/meshes/0/detailed'
