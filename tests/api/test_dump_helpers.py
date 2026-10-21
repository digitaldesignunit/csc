"""The helpers of the local dump folders (tests/api/support.py): which folder
is the newest, and an export file with no documents (0 bytes) loads as none,
a collection with no export file is not loaded."""

from __future__ import annotations

import json

from support import dump_files, latest_dump, load_dump, read_export


def test_the_latest_dump_is_the_greatest_six_digit_folder(tmp_path):
    for name in ('260520', '261009', '261020', '261016'):
        (tmp_path / name).mkdir()
    assert latest_dump(str(tmp_path)) == '261020'


def test_folders_that_are_not_six_digits_and_files_are_not_dumps(tmp_path):
    for name in ('261009', 'archive', '2610200', '99999', 'backup-261231'):
        (tmp_path / name).mkdir()
    (tmp_path / '261231').write_text('a file, not a dump', encoding='utf-8')
    assert latest_dump(str(tmp_path)) == '261009'


def test_no_dump_and_no_folder_give_none(tmp_path):
    assert latest_dump(str(tmp_path)) is None
    assert latest_dump(str(tmp_path / 'missing')) is None


def test_an_export_file_of_zero_bytes_has_no_documents(tmp_path):
    empty = tmp_path / 'csc.access_tokens.json'
    empty.write_bytes(b'')
    assert read_export(str(empty)) == []
    blank = tmp_path / 'csc.blank.json'
    blank.write_text('  \r\n\n', encoding='utf-8')
    assert read_export(str(blank)) == []


def test_an_export_file_with_documents_is_read(tmp_path):
    path = tmp_path / 'csc.datasets.json'
    path.write_text(json.dumps([{'_id': 'a'}, {'_id': 'b'}]), encoding='utf-8')
    assert [d['_id'] for d in read_export(str(path))] == ['a', 'b']
    path.write_text('[]', encoding='utf-8')
    assert read_export(str(path)) == []


class FakeCollection:
    def __init__(self):
        self.docs = []

    def delete_many(self, _filter):
        self.docs = []

    def insert_many(self, docs, ordered=True):
        self.docs.extend(docs)


class FakeDatabase(dict):
    def __missing__(self, name):
        self[name] = FakeCollection()
        return self[name]


def test_a_dump_with_an_empty_file_and_a_missing_collection_loads(tmp_path):
    (tmp_path / 'csc.datasets.json').write_text(json.dumps([{'_id': 'a'}]), encoding='utf-8')
    (tmp_path / 'csc.access_tokens.json').write_bytes(b'')       # exported, no documents
    # csc.invitations.json is not there at all: the dump predates it
    database = FakeDatabase()
    counts = load_dump(database, str(tmp_path))
    assert counts == {'access_tokens': 0, 'datasets': 1}
    assert [d['_id'] for d in database['datasets'].docs] == ['a']
    assert database['access_tokens'].docs == []
    assert 'invitations' not in counts and sorted(dump_files(str(tmp_path))) == ['access_tokens', 'datasets']
