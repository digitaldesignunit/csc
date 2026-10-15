"""fetch.py: every file of the Zenodo record, checked against its MD5; no network (a local fake record and
a fake opener serve the bytes)."""

from __future__ import annotations

import hashlib
import io
import json

import pytest

FILES = {'Wall Data - Test.xlsx': b'wall bytes\r\nwith a CR', 'Guidelines.pdf': b'%PDF-1.7 fake'}


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def record_of(files=FILES, checksums=None, licence='cc-by-4.0'):
    checksums = checksums or {}
    return {'doi': '10.5281/zenodo.0', 'metadata': {'license': {'id': licence}},
            'files': [{'key': name, 'size': len(data),
                       'checksum': checksums.get(name, 'md5:' + md5(data)),
                       'links': {'self': f'https://zenodo.org/api/records/0/files/{name}/content'}}
                      for name, data in files.items()]}


class Opener:
    """Serves the bytes of the fake files by URL and remembers what was asked for."""

    def __init__(self, files=FILES, corrupt=()):
        self.files, self.corrupt, self.asked = files, set(corrupt), []

    def __call__(self, url):
        self.asked.append(url)
        name = url.split('/files/')[1].rsplit('/content', 1)[0]
        data = self.files[name]
        if name in self.corrupt:
            data = data + b'X'                      # arrives damaged
        return Response(data)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_every_file_is_fetched_and_checked(fetch_module, tmp_path):
    opener = Opener()
    done = fetch_module.sync(record_of(), tmp_path / 'data', opener, log=lambda _m: None)
    assert sorted(done['fetched']) == sorted(FILES) and done['refused'] == [] and done['skipped'] == []
    for name, data in FILES.items():
        assert (tmp_path / 'data' / name).read_bytes() == data
    assert not list((tmp_path / 'data').glob('*.part'))             # no temporary file is left


def test_a_file_whose_sum_does_not_match_is_refused_and_deleted(fetch_module, tmp_path):
    opener = Opener(corrupt={'Guidelines.pdf'})
    done = fetch_module.sync(record_of(), tmp_path / 'data', opener, log=lambda _m: None)
    assert done['refused'] == ['Guidelines.pdf'] and done['fetched'] == ['Wall Data - Test.xlsx']
    assert not (tmp_path / 'data' / 'Guidelines.pdf').exists()
    assert not list((tmp_path / 'data').glob('*.part'))
    assert (tmp_path / 'data' / 'Wall Data - Test.xlsx').exists()   # the good one stays


def test_a_wrong_sum_in_the_record_is_refused_the_same_way(fetch_module, tmp_path):
    record = record_of(checksums={'Guidelines.pdf': 'md5:' + '0' * 32})
    done = fetch_module.sync(record, tmp_path / 'data', Opener(), log=lambda _m: None)
    assert done['refused'] == ['Guidelines.pdf']
    assert not (tmp_path / 'data' / 'Guidelines.pdf').exists()


def test_an_old_file_that_does_not_match_is_replaced_or_deleted(fetch_module, tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'Guidelines.pdf').write_bytes(b'an old, damaged copy')
    done = fetch_module.sync(record_of(), data, Opener(), log=lambda _m: None)
    assert 'Guidelines.pdf' in done['fetched']
    assert (data / 'Guidelines.pdf').read_bytes() == FILES['Guidelines.pdf']
    # and when the new download is damaged too, the old damaged one does not stay either
    (data / 'Guidelines.pdf').write_bytes(b'damaged again')
    done = fetch_module.sync(record_of(), data, Opener(corrupt={'Guidelines.pdf'}), log=lambda _m: None)
    assert done['refused'] == ['Guidelines.pdf'] and not (data / 'Guidelines.pdf').exists()


def test_a_second_run_fetches_nothing(fetch_module, tmp_path):
    first = Opener()
    fetch_module.sync(record_of(), tmp_path / 'data', first, log=lambda _m: None)
    second = Opener()
    done = fetch_module.sync(record_of(), tmp_path / 'data', second, log=lambda _m: None)
    assert sorted(done['skipped']) == sorted(FILES) and done['fetched'] == []
    assert second.asked == []                                       # not even a request


def test_the_checksum_is_read_with_whitespace_and_carriage_returns_stripped(fetch_module):
    digest = md5(b'x')
    assert fetch_module.expected_md5(f' md5:{digest.upper()}\r\n') == digest
    assert fetch_module.expected_md5(f'MD5: {digest}\r') == digest
    for bad in ('sha256:abc', 'md5:', digest, ''):
        with pytest.raises(ValueError):
            fetch_module.expected_md5(bad)


def test_a_file_name_cannot_leave_the_destination(fetch_module, tmp_path):
    for key in ('../evil.xlsx', 'a/b.xlsx', 'a\\b.xlsx', '..', ''):
        with pytest.raises(ValueError):
            fetch_module.safe_name(key)
        record = record_of(files={'ok.bin': b'1'})
        record['files'][0]['key'] = key
        with pytest.raises(ValueError):
            fetch_module.sync(record, tmp_path / 'data', Opener(), log=lambda _m: None)
    assert fetch_module.safe_name('Wall Data - Dutch.xlsx') == 'Wall Data - Dutch.xlsx'


def test_main_writes_the_record_beside_the_folder_and_exits_with_the_result(fetch_module, tmp_path, capsys):
    record_file = tmp_path / 'in.json'
    record_file.write_text(json.dumps(record_of()), encoding='utf-8')
    dest = tmp_path / 'recreate' / 'zenodo-0'
    code = fetch_module.main(['--dest', str(dest), '--record-file', str(record_file)], Opener())
    assert code == 0
    written = json.loads((tmp_path / 'recreate' / 'record.json').read_text(encoding='utf-8'))
    assert [f['key'] for f in written['files']] == list(FILES)
    assert 'Attribution (CC BY 4.0)' in capsys.readouterr().out
    bad = fetch_module.main(['--dest', str(tmp_path / 'again' / 'zenodo-0'),
                             '--record-file', str(record_file)], Opener(corrupt={'Guidelines.pdf'}))
    assert bad == 1


def test_another_licence_is_warned_about(fetch_module, tmp_path, capsys):
    record_file = tmp_path / 'in.json'
    record_file.write_text(json.dumps(record_of(licence='cc-by-nc-4.0')), encoding='utf-8')
    fetch_module.main(['--dest', str(tmp_path / 'd' / 'z'), '--record-file', str(record_file)], Opener())
    assert "warning: the licence is 'cc-by-nc-4.0'" in capsys.readouterr().out


def test_main_refuses_to_write_into_the_repository_outside_dev(fetch_module, common, tmp_path):
    with pytest.raises(SystemExit) as stop:
        fetch_module.main(['--dest', str(common.REPO / 'scripts' / 'data'), '--record-file',
                           str(tmp_path / 'none.json')], Opener())
    assert 'refusing to write inside the repository' in str(stop.value)


# THE URL OF A FILE (review note) ---------------------------------------------------
@pytest.mark.parametrize('url', [
    'https://zenodo.org/api/records/1/files/a.xlsx/content',
    'https://www.zenodo.org/api/records/1/files/a.xlsx/content',
    'https://sandbox.zenodo.org/records/1/files/a.xlsx',
    'HTTPS://ZENODO.ORG/x'])
def test_https_zenodo_urls_are_accepted(fetch_module, url):
    assert fetch_module.url_problem(url) == ''


@pytest.mark.parametrize('url, why', [
    ('file:///C:/Windows/win.ini', 'not https (file)'),
    ('http://zenodo.org/api/records/1/files/a/content', 'not https (http)'),
    ('ftp://zenodo.org/a', 'not https (ftp)'),
    ('//zenodo.org/a', 'not https (no scheme)'),
    ('https://evil.example/a', 'host is not zenodo.org (evil.example)'),
    ('https://zenodo.org.evil.example/a', 'host is not zenodo.org (zenodo.org.evil.example)'),
    ('https://notzenodo.org/a', 'host is not zenodo.org (notzenodo.org)'),
    ('https://zenodo.org@evil.example/a', 'host is not zenodo.org (evil.example)'),
    ('', 'not https (no scheme)')])
def test_any_other_url_is_refused_with_a_reason(fetch_module, url, why):
    assert why in fetch_module.url_problem(url)


def test_a_record_that_names_a_file_or_http_url_is_refused_and_nothing_is_fetched(fetch_module, tmp_path):
    record = record_of(files={'a.bin': b'1', 'b.bin': b'2', 'c.bin': b'3'})
    record['files'][0]['links']['self'] = 'file:///C:/Windows/win.ini'
    record['files'][1]['links']['self'] = 'http://zenodo.org/api/records/0/files/b.bin/content'
    opener, lines = Opener(files={'c.bin': b'3'}), []
    done = fetch_module.sync(record, tmp_path / 'data', opener, log=lines.append)
    assert done['refused'] == ['a.bin', 'b.bin'] and done['fetched'] == ['c.bin']
    assert len(opener.asked) == 1 and opener.asked[0].endswith('/c.bin/content')   # only the https one
    assert not (tmp_path / 'data' / 'a.bin').exists() and not (tmp_path / 'data' / 'b.bin').exists()
    assert any('REFUSED a.bin: the URL is not https (file)' in line for line in lines)
    assert any('REFUSED b.bin: the URL is not https (http)' in line for line in lines)


def test_main_exits_with_1_for_a_refused_url(fetch_module, tmp_path):
    record = record_of(files={'a.bin': b'1'})
    record['files'][0]['links']['self'] = 'file:///etc/passwd'
    record_file = tmp_path / 'in.json'
    record_file.write_text(json.dumps(record), encoding='utf-8')
    opener = Opener(files={})
    assert fetch_module.main(['--dest', str(tmp_path / 'd' / 'z'), '--record-file', str(record_file)],
                             opener) == 1
    assert opener.asked == []
