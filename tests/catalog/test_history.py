"""The change log: diff and point-in-time rollback (section 3.8, I30)."""

from __future__ import annotations

from apps.catalog.history import as_of, diff


def test_diff_lists_changed_fields_and_skips_derived_ones():
    before = {'_id': 'i', 'trade_name': 'A', 'properties': {'x': 1},
              'origin': {'kind': 'unknown'}, 'lastmodified': '1'}
    after = {'_id': 'i', 'trade_name': 'B', 'properties': {'x': 2},
             'origin': {'kind': 'unknown'}, 'lastmodified': '2',
             'manufacturer': 'M'}
    assert diff('identity', before, after) == [
        {'path': 'manufacturer', 'old': None, 'new': 'M'},
        {'path': 'trade_name', 'old': 'A', 'new': 'B'}]


def test_snapshot_status_is_left_to_its_history():
    assert diff('snapshot', {'status': 'draft', 'name': 'a'},
                {'status': 'pending', 'name': 'a'}) == []


def test_as_of_undoes_later_entries_newest_first():
    doc = {'_id': 'i', 'trade_name': 'C', 'manufacturer': 'M',
           'properties': {'x': 1}, 'created': '2026-01-01T00:00:00Z'}
    entries = [
        {'record_kind': 'identity', 'at': '2026-02-01T00:00:00Z',
         'changes': [{'path': 'trade_name', 'old': 'A', 'new': 'B'}]},
        {'record_kind': 'identity', 'at': '2026-03-01T00:00:00Z',
         'changes': [{'path': 'trade_name', 'old': 'B', 'new': 'C'},
                     {'path': 'manufacturer', 'old': None, 'new': 'M'}]},
    ]
    then = as_of('identity', doc, entries, '2026-01-15T00:00:00Z')
    assert then['trade_name'] == 'A'
    assert 'manufacturer' not in then
    assert 'properties' not in then
    mid = as_of('identity', doc, entries, '2026-02-15T00:00:00Z')
    assert mid['trade_name'] == 'B'


def test_as_of_reads_a_snapshot_status_from_its_history():
    doc = {'_id': 's', 'status': 'published', 'status_history': [
        {'from': 'draft', 'to': 'pending', 'at': '2026-01-02T00:00:00Z',
         'by_user_id': 'u'},
        {'from': 'pending', 'to': 'published', 'at': '2026-01-03T00:00:00Z',
         'by_user_id': 'm'}]}
    assert as_of('snapshot', doc, [], '2026-01-01T00:00:00Z')['status'] \
        == 'draft'
    assert as_of('snapshot', doc, [], '2026-01-02T12:00:00Z')['status'] \
        == 'pending'
    migrated = {'_id': 's', 'status': 'published', 'status_history': []}
    assert as_of('snapshot', migrated, [], '2020-01-01T00:00:00Z')[
        'status'] == 'published'
