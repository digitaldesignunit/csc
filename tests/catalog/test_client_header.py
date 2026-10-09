"""X-CSC-Client parsing (data model spec section 7.4)."""

from apps.catalog.client_header import describe_client, parse_client_header


def test_well_formed_headers_parse():
    assert parse_client_header('gh-userobjects/0.5.1.0') == (
        'gh-userobjects', '0.5.1.0')
    assert parse_client_header('web/0.6.0.0') == ('web', '0.6.0.0')
    assert parse_client_header('  web/1  ') == ('web', '1')


def test_malformed_headers_are_rejected():
    for value in (None, '', 'web', 'web/', '/0.5', 'Web/0.5', 'web/v0.5',
                  'web/0.5.1.0.1', 'web 0.5', 'web/0.5; rm -rf'):
        assert parse_client_header(value) is None, value


def test_describe_names_client_or_falls_back_to_user_agent():
    assert describe_client('web/0.5.1.0', 'Mozilla') == (
        'client=web version=0.5.1.0')
    assert describe_client(None, 'python-requests/2.32') == (
        "client=unknown agent='python-requests/2.32'")
    assert describe_client('nonsense', None) == "client=invalid raw='nonsense'"


# ENFORCEMENT (decision 8.11) -------------------------------------------------
import pytest  # noqa: E402

from apps.catalog.client_header import (  # noqa: E402
    parse_min_versions,
    rejection,
    version_tuple,
)

TABLE = {'gh-userobjects': (0, 6, 0, 0), 'web': (0, 6, 0, 0)}


def test_min_versions_parse():
    assert parse_min_versions(None) == {}
    assert parse_min_versions(' gh-userobjects=0.6.0.0 , web=0.6 ') == TABLE
    with pytest.raises(ValueError):
        parse_min_versions('web')
    assert version_tuple('0.6') < version_tuple('0.6.0.1')


def test_without_a_table_nothing_is_refused():
    assert rejection('POST', '/identities', None, True, {}) is None


@pytest.mark.parametrize('method, header, authenticated, refused', [
    # writes and logged-in requests: a known, current client is required
    ('POST', 'gh-userobjects/0.6.0.0', True, False),
    ('POST', None, True, True),
    ('PATCH', None, False, True),              # a write without a token too
    ('GET', None, True, True),                 # logged-in read (old GH, pre-0.5.1)
    ('GET', 'my-script/1.0', True, True),      # unknown client, logged in
    ('DELETE', 'web/0.6.0.1', True, False),
    # anonymous reads: the header is optional
    ('GET', None, False, False),
    ('HEAD', None, False, False),
    ('GET', 'my-script/1.0', False, False),
    ('GET', 'garbage', False, False),
    # a known client below its minimum: always refused
    ('GET', 'gh-userobjects/0.5.1.0', False, True),
    ('GET', 'web/0.5.1.0', True, True),
    ('POST', 'gh-userobjects/0.5.1.0', True, True),
])
def test_enforcement_table(method, header, authenticated, refused):
    reason = rejection(method, '/identities/abc', header, authenticated, TABLE)
    assert (reason is not None) is refused


@pytest.mark.parametrize('path', [
    '/ghinterface/userobject/DDU_CSC_Update', '/ghinterface/version',
    '/ghinterface', '/docs', '/openapi.json', '/health/db', '/version',
    '/auth/token',
])
def test_exempt_paths_and_preflight(path):
    assert rejection('GET', path, 'gh-userobjects/0.5.1.0', True, TABLE) is None
    assert rejection('OPTIONS', '/identities', None, False, TABLE) is None


def test_refusal_names_the_fix():
    reason = rejection('GET', '/identities', 'gh-userobjects/0.5.1.0', True,
                       TABLE)
    assert '0.6.0.0' in reason and 'CSC_Update' in reason


def test_login_is_open_to_an_outdated_client_but_only_login():
    """A 0.5 Session must reach /auth/token to log in and run CSC_Update
    (8.95 11); nothing else of /auth is exempt."""
    old = 'gh-userobjects/0.5.1.0'
    assert rejection('POST', '/auth/token', old, False, TABLE) is None
    assert rejection('POST', '/auth/token', None, False, TABLE) is None
    assert rejection('POST', '/auth/change-password', old, True, TABLE)
    assert rejection('POST', '/auth/register', old, False, TABLE)
