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


# S4 (8.144): the exact-match filters are text, not patterns ------------------
def test_exact_filters_escape_the_value():
    import re
    match = CatalogFilters(original_function='.*', material='a(b+)+$',
                           dataset='x|y').identity_match()
    for name, value in (('original_function', '.*'), ('material', 'a(b+)+$'),
                        ('dataset', 'x|y')):
        assert match[name]['$regex'] == f'^{re.escape(value)}$'
        assert match[name]['$options'] == 'i'


def test_text_filters_have_a_length_cap():
    from apps.catalog.api.identity_filters import FILTER_MAX_LENGTH
    import inspect
    from apps.catalog.api.identity_filters import catalog_filters
    for name in ('original_function', 'material', 'dataset', 'q'):
        default = inspect.signature(catalog_filters).parameters[name].default
        lengths = [m.max_length for m in default.metadata
                   if hasattr(m, 'max_length')]
        assert lengths == [FILTER_MAX_LENGTH], name


def test_a_dimension_search_is_not_part_of_the_default_scope():
    from apps.catalog.api.identity_filters import _parse_fit
    assert CatalogFilters().fit_pipeline_stages() == []
    fit = _parse_fit('about', '200,1200,600', None)
    assert fit == {'fit_mode': 'about', 'fit_sides': (1200.0, 600.0, 200.0),
                   'fit_tolerance': ('percent', 10.0)}
    filters = CatalogFilters(**fit)
    assert not filters.is_default_scope()
    assert filters.snapshot_match() == {'current_snapshot.status': 'published'}
    stages = filters.fit_pipeline_stages()
    assert [next(iter(stage)) for stage in stages] == [
        '$match', '$addFields', '$match', '$addFields', '$unset']
    assert _parse_fit('can_hold', '1,2,3', None)['fit_tolerance'] is None
    assert _parse_fit(None, None, None) == {}


def test_a_near_search_opens_the_pipeline_with_geonear_that_carries_the_match():
    from apps.catalog.api.identity_query import build_list_pipeline
    from apps.catalog.api.identity_filters import SORT_KEYS
    assert 'distance' in SORT_KEYS
    plain = CatalogFilters()
    assert plain.near is None
    assert plain.opening_stages({'exit': None}) == [{'$match': {'exit': None}}]
    filters = CatalogFilters(near_lat=49.9, near_lon=8.6, near_layer='origin', radius_km=2)
    assert filters.near == (49.9, 8.6, 'origin', 2)
    assert not filters.is_default_scope()
    stage = filters.opening_stages({'exit': None})[0]['$geoNear']
    assert stage['near'] == {'type': 'Point', 'coordinates': [8.6, 49.9]}   # lon first
    assert stage['key'] == 'geo_origin' and stage['maxDistance'] == 2000
    assert stage['query'] == {'exit': None} and stage['spherical'] is True
    assert stage['distanceField'] == 'distance_m'
    # without a layer it is the current one, without a radius there is no limit
    nearest = CatalogFilters(near_lat=0, near_lon=0).opening_stages({})[0]['$geoNear']
    assert nearest['key'] == 'geo_current' and 'maxDistance' not in nearest
    pipeline = build_list_pipeline(
        snapshots_collection='s', identity_match={'exit': None}, snapshot_match={},
        sortkey='distance', sort_order=1, page=1, size=10, include_username=False,
        current_user_id=None, reserved_filter=None, near=filters.near)
    assert '$geoNear' in pipeline[0]
    # the sort runs on the small identity documents, right after the first stage
    assert pipeline[1] == {'$sort': {'distance_m': 1, 'catalog_number': 1, '_id': 1}}
    assert '$lookup' in pipeline[2]
