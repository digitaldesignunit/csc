"""The catalog filters (spec section 7) as Mongo match stages."""

from apps.catalog.api.identity_filters import (
    CatalogFilters,
    children_identity_match,
    resolve_sort_field,
)


def test_children_match_finds_parent_without_circulation_filter():
    match = children_identity_match('parent-id')
    assert match == {'parent_identities': 'parent-id'}


def test_children_match_restricts_to_public_for_anonymous():
    match = children_identity_match('parent-id', public_only=True)
    assert match == {'parent_identities': 'parent-id', 'is_public': True}


def test_default_scope_is_the_public_catalog_view():
    filters = CatalogFilters()
    assert filters.identity_match() == {'exit': None, 'withdrawn': None}
    assert filters.snapshot_match() == {'current_snapshot.status': 'published'}
    assert filters.is_default_scope()


def test_filters_map_to_06_fields():
    filters = CatalogFilters(original_function='IfcBeam', circulation='exited',
                             exit_kind='split', include_withdrawn=True,
                             material_class='17 01 01', reserved='true',
                             status='any', shape_class='linear', bbx_min_x=100,
                             bbx_max_x=6000)
    assert filters.identity_match() == {
        'exit': {'$ne': None}, 'exit.kind': 'split',
        'original_function': {'$regex': '^IfcBeam$', '$options': 'i'},
        'material_class': '17 01 01', 'reserved': {'$ne': ''}}
    assert filters.snapshot_match() == {
        'current_snapshot.shape_class': 'linear',
        'current_snapshot.bbx.0': {'$gte': 100, '$lte': 6000}}
    assert CatalogFilters(circulation='all').identity_match() == {'withdrawn': None}


def test_sort_keys():
    assert resolve_sort_field('original_function') == 'original_function'
    assert resolve_sort_field('effective_from') == 'current_snapshot.effective_from'
    assert resolve_sort_field('type') == '_id'           # 0.5 key, gone


def test_circulation_splits_in_place_from_deinstalled():
    """Active = no exit; the sub-values tell the planned origin apart."""
    assert CatalogFilters(circulation='active').identity_match() == {
        'exit': None, 'withdrawn': None}
    assert CatalogFilters(circulation='in_place').identity_match() == {
        'exit': None, 'origin.planned': True, 'withdrawn': None}
    assert CatalogFilters(circulation='deinstalled').identity_match() == {
        'exit': None, 'origin.planned': {'$ne': True}, 'withdrawn': None}
    assert CatalogFilters(circulation='exited').identity_match() == {
        'exit': {'$ne': None}, 'withdrawn': None}
