"""Tests for Grasshopper component source version parsing."""

from apps.catalog.api.ghinterface import (
    compare_versions,
    get_source_version,
)


def test_version_declaration_is_parsed():
    assert get_source_version('    Version: 260611') == (260611, 0, 0)


def test_dotted_and_lettered_versions_are_parsed():
    assert get_source_version('Version: 251009.1') == (251009, 1, 0)
    assert get_source_version('Version: 251009a') == (251009, 0, 1)


def test_prose_mentioning_version_does_not_shadow_declaration():
    source = (
        "ghenv.Component.Description = (\n"
        "    'Creates a catalog identity and version-0 snapshot via "
        "POST /identities. '\n"
        ")\n"
        '    Version: 260611\n'
    )
    assert get_source_version(source) == (260611, 0, 0)


def test_source_without_declaration_has_no_version():
    source = 'Snapshot UUIDs (ordered by version)\nreturn 0\n'
    assert get_source_version(source) is None


def test_newer_server_version_compares_greater():
    server = get_source_version('Version: 260611')
    document = get_source_version('Version: 260610')
    assert compare_versions(server, document) == 1
    assert compare_versions(document, server) == -1
    assert compare_versions(server, server) == 0
