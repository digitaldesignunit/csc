"""`.zenodo.json` follows VERSION and the CHANGELOG (scripts/ci/zenodo_metadata.py)."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    'zenodo_metadata', ROOT / 'scripts' / 'ci' / 'zenodo_metadata.py')
zenodo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(zenodo)


def test_the_changelog_subset_becomes_html():
    out = zenodo.to_html(
        'An intro line\nthat wraps.\n\n### Changed\n\n'
        '- **Bold** with `code <x>` and a\nwrapped line\n'
        '- a [link](https://example.org/a) and *emphasis*\n')
    assert out == (
        '<p>An intro line that wraps.</p><h3>Changed</h3><ul>'
        '<li><strong>Bold</strong> with <code>code &lt;x&gt;</code> and a '
        'wrapped line</li>'
        '<li>a <a href="https://example.org/a">link</a> and '
        '<em>emphasis</em></li></ul>')


def test_the_committed_file_matches_the_version():
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    data = json.loads((ROOT / '.zenodo.json').read_text(encoding='utf-8'))
    wanted = zenodo.generated(version)
    assert data['version'] == version
    assert data['title'] == wanted['title']
    assert data['title'].startswith(zenodo.TITLE)
    assert data['description'] == wanted['description']
    assert data['upload_type'] == 'software'
    assert data['creators'] and data['contributors']
