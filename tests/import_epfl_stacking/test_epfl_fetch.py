"""fetch.py: the archive of the Zenodo record, its MD5, and a checked extraction; no network (a fake record
and a fake opener serve the bytes)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest


def make_zip(files, path=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    data = buffer.getvalue()
    if path is not None:
        path.write_bytes(data)
    return data


GOOD = {'repo-abc123/README.md': b'readme', 'repo-abc123/stones/mesh_high_res/m_A0.ply': b'ply\n',
        'repo-abc123/stones/pcd_high_res/p_A0.ply': b'ply\n'}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def record_of(data, key='owner/repo-v1.zip', url=None, checksum=None):
    return {'doi': '10.5281/zenodo.0', 'metadata': {'license': {'id': 'other-open'}},
            'files': [{'key': key, 'size': len(data), 'checksum': checksum or 'md5:' + hashlib.md5(data).hexdigest(),
                       'links': {'self': url or f'https://zenodo.org/api/records/0/files/{key}/content'}}]}


class Opener:
    def __init__(self, data, corrupt=False):
        self.data, self.corrupt, self.asked = data, corrupt, []

    def __call__(self, url):
        self.asked.append(url)
        return Response(self.data + (b'X' if self.corrupt else b''))


def write_record(tmp_path, record):
    path = tmp_path / 'record.json'
    path.write_text(json.dumps(record), encoding='utf-8')
    return path


# THE KEY OF THE RECORD HAS A FOLDER ----------------------------------------------------------
def test_a_key_with_a_folder_lands_flat_in_the_destination(fetch_module):
    assert fetch_module.flat_name('ibois-epfl/augmented-stacking-dataset-v1.zip') == \
        'augmented-stacking-dataset-v1.zip'
    assert fetch_module.flat_name('plain.zip') == 'plain.zip'
    for bad in ('../x.zip', 'a/../x.zip', 'a//b.zip', '/abs.zip', 'a\\b.zip', '', '..'):
        with pytest.raises(ValueError):
            fetch_module.flat_name(bad)


# THE CHECKED EXTRACTION -----------------------------------------------------------------------
@pytest.mark.parametrize('name, why', [
    ('../evil.txt', 'parent folder'), ('a/../../evil.txt', 'parent folder'), ('/abs/evil.txt', 'absolute path'),
    ('C:/evil.txt', 'drive letter'), ('C:evil.txt', 'drive letter'), ('a\\evil.txt', 'backslash'),
    ('\\\\server\\share\\x', 'backslash'), ('', 'empty')])
def test_a_member_name_that_could_leave_the_folder_is_named_a_problem(fetch_module, name, why):
    assert why in fetch_module.member_problem(name)


@pytest.mark.parametrize('name', ['repo/README.md', 'repo/stones/mesh_high_res/a.ply', 'a.txt', 'a b/c d.ply'])
def test_ordinary_member_names_are_fine(fetch_module, name):
    assert fetch_module.member_problem(name) == ''


@pytest.mark.parametrize('evil', ['../evil.txt', '/abs-evil.txt', 'C:/evil.txt', 'ok/../../evil.txt'])
def test_an_archive_with_such_a_name_is_refused_and_nothing_is_written(fetch_module, tmp_path, evil):
    archive = tmp_path / 'bad.zip'
    make_zip({'repo/fine.txt': b'fine', evil: b'evil'}, archive)
    target = tmp_path / 'unpacked'
    with pytest.raises(ValueError) as stop:
        fetch_module.extract(archive, target, log=lambda _m: None)
    assert 'refusing to extract' in str(stop.value)
    assert not target.exists() or not any(target.rglob('*'))                  # not even the fine file
    assert not (tmp_path / 'evil.txt').exists() and not (tmp_path.parent / 'evil.txt').exists()


def test_a_good_archive_is_extracted_and_a_second_run_writes_nothing(fetch_module, tmp_path):
    archive = tmp_path / 'good.zip'
    make_zip(GOOD, archive)
    first = fetch_module.extract(archive, tmp_path / 'unpacked', log=lambda _m: None)
    assert first['written'] == 3
    assert (tmp_path / 'unpacked' / 'repo-abc123' / 'README.md').read_bytes() == b'readme'
    second = fetch_module.extract(archive, tmp_path / 'unpacked', log=lambda _m: None)
    assert second['written'] == 0 and second['present'] == 3
    (tmp_path / 'unpacked' / 'repo-abc123' / 'README.md').write_bytes(b'cut')   # damaged: another size
    third = fetch_module.extract(archive, tmp_path / 'unpacked', log=lambda _m: None)
    assert third['written'] == 1 and (tmp_path / 'unpacked' / 'repo-abc123' / 'README.md').read_bytes() == b'readme'


def test_too_many_members_or_too_much_data_is_refused(fetch_module, tmp_path, monkeypatch):
    archive = tmp_path / 'many.zip'
    make_zip({f'f{i}.txt': b'x' for i in range(5)}, archive)
    monkeypatch.setattr(fetch_module, 'MAX_MEMBERS', 3)
    with pytest.raises(ValueError, match='5 members'):
        fetch_module.extract(archive, tmp_path / 'u', log=lambda _m: None)
    monkeypatch.setattr(fetch_module, 'MAX_MEMBERS', 100)
    monkeypatch.setattr(fetch_module, 'MAX_UNPACKED_BYTES', 3)
    with pytest.raises(ValueError, match='GB unpacked'):
        fetch_module.extract(archive, tmp_path / 'u', log=lambda _m: None)


def test_the_bytes_actually_written_are_counted_whatever_the_archive_declares(fetch_module, tmp_path, monkeypatch):
    """The declared sizes pass (the check of the central directory is switched off, as a lying archive would
    get past it); the limit is enforced in the write loop: the partial member is deleted, the earlier ones
    stay, and the extraction stops."""
    archive = tmp_path / 'big.zip'
    make_zip({'repo/small.txt': b'abc', 'repo/big.bin': b'x' * 40, 'repo/after.txt': b'later'}, archive)
    monkeypatch.setattr(fetch_module, 'check_archive', lambda _a: [])
    monkeypatch.setattr(fetch_module, 'MAX_UNPACKED_BYTES', 10)
    monkeypatch.setattr(fetch_module, 'CHUNK', 4)
    target = tmp_path / 'unpacked'
    with pytest.raises(ValueError, match='more than 10 bytes written'):
        fetch_module.extract(archive, target, log=lambda _m: None)
    assert (target / 'repo' / 'small.txt').read_bytes() == b'abc'
    assert not (target / 'repo' / 'big.bin').exists()                      # the partial member is gone
    assert not (target / 'repo' / 'after.txt').exists()                    # and nothing after it


def test_the_running_total_counts_across_members_not_per_member(fetch_module, tmp_path, monkeypatch):
    archive = tmp_path / 'many.zip'
    make_zip({f'repo/f{i}.bin': b'y' * 4 for i in range(5)}, archive)       # each is under the limit
    monkeypatch.setattr(fetch_module, 'check_archive', lambda _a: [])
    monkeypatch.setattr(fetch_module, 'MAX_UNPACKED_BYTES', 10)
    with pytest.raises(ValueError, match='more than 10 bytes'):
        fetch_module.extract(archive, tmp_path / 'u', log=lambda _m: None)
    written = sorted(p.name for p in (tmp_path / 'u' / 'repo').iterdir())
    assert written == ['f0.bin', 'f1.bin']                                   # 4 + 4 = 8; the third passes 10


def test_an_archive_that_stays_under_the_limit_is_unaffected(fetch_module, tmp_path, monkeypatch):
    archive = tmp_path / 'ok.zip'
    make_zip({'repo/a.bin': b'z' * 10}, archive)
    monkeypatch.setattr(fetch_module, 'MAX_UNPACKED_BYTES', 10)             # exactly the limit: allowed
    assert fetch_module.extract(archive, tmp_path / 'u', log=lambda _m: None)['written'] == 1


def test_main_exits_with_1_when_the_write_limit_is_passed(fetch_module, tmp_path, monkeypatch, capsys):
    data = make_zip({'repo/big.bin': b'x' * 40})
    record_file = write_record(tmp_path, record_of(data))
    monkeypatch.setattr(fetch_module, 'check_archive', lambda _a: [])
    monkeypatch.setattr(fetch_module, 'MAX_UNPACKED_BYTES', 10)
    dest = tmp_path / 'e' / 'z'
    assert fetch_module.main(['--dest', str(dest), '--record-file', str(record_file)], Opener(data)) == 1
    assert 'REFUSED repo-v1.zip' in capsys.readouterr().out
    assert not (dest / 'unpacked' / 'repo' / 'big.bin').exists()


# THE WHOLE STEP -------------------------------------------------------------------------------
def test_main_fetches_checks_and_unpacks_into_the_destination(fetch_module, tmp_path, capsys):
    data = make_zip(GOOD)
    record_file = write_record(tmp_path, record_of(data))
    dest = tmp_path / 'epfl' / 'zenodo-0'
    opener = Opener(data)
    code = fetch_module.main(['--dest', str(dest), '--record-file', str(record_file)], opener)
    assert code == 0 and len(opener.asked) == 1
    assert (dest / 'repo-v1.zip').read_bytes() == data              # the folder of the key is dropped
    assert (dest / 'unpacked' / 'repo-abc123' / 'stones' / 'pcd_high_res' / 'p_A0.ply').is_file()
    assert json.loads((dest.parent / 'record.json').read_text(encoding='utf-8'))['files'][0]['key'] == \
        'owner/repo-v1.zip'
    assert 'Attribution (MIT licence)' in capsys.readouterr().out
    # idempotent: no second download
    again = Opener(data)
    assert fetch_module.main(['--dest', str(dest), '--record-file', str(record_file)], again) == 0
    assert again.asked == []


def test_a_damaged_download_is_refused_deleted_and_not_unpacked(fetch_module, tmp_path):
    data = make_zip(GOOD)
    record_file = write_record(tmp_path, record_of(data))
    dest = tmp_path / 'epfl' / 'zenodo-0'
    code = fetch_module.main(['--dest', str(dest), '--record-file', str(record_file)], Opener(data, corrupt=True))
    assert code == 1
    assert not (dest / 'repo-v1.zip').exists() and not (dest / 'unpacked').exists()


@pytest.mark.parametrize('url', ['file:///C:/Windows/win.ini', 'http://zenodo.org/api/x', 'https://evil.example/a.zip'])
def test_a_record_that_names_another_url_is_refused_without_a_request(fetch_module, tmp_path, url):
    data = make_zip(GOOD)
    record_file = write_record(tmp_path, record_of(data, url=url))
    opener = Opener(data)
    code = fetch_module.main(['--dest', str(tmp_path / 'e' / 'z'), '--record-file', str(record_file)], opener)
    assert code == 1 and opener.asked == []


def test_a_zip_with_a_bad_name_stops_the_step_with_1(fetch_module, tmp_path, capsys):
    data = make_zip({'repo/ok.txt': b'ok', '../evil.txt': b'evil'})
    record_file = write_record(tmp_path, record_of(data))
    dest = tmp_path / 'e' / 'z'
    assert fetch_module.main(['--dest', str(dest), '--record-file', str(record_file)], Opener(data)) == 1
    assert 'REFUSED repo-v1.zip' in capsys.readouterr().out
    assert not (dest / 'unpacked').exists() or not any((dest / 'unpacked').rglob('*'))
    assert not (tmp_path / 'e' / 'evil.txt').exists()


def test_the_destination_must_not_be_in_the_repository_outside_dev(fetch_module, epfl, tmp_path):
    with pytest.raises(SystemExit) as stop:
        fetch_module.main(['--dest', str(epfl.common.REPO / 'scripts' / 'data'),
                           '--record-file', str(tmp_path / 'none.json')], Opener(b''))
    assert 'refusing to write inside the repository' in str(stop.value)
