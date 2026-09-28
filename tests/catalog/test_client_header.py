"""X-CSC-Client parsing (data model spec §7.4)."""

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
