"""The pure parts of ``invoke release-prep`` and ``bump-version --gh``
(scripts/ci/release_prep.py): the CHANGELOG date, the empty-section rule, and
the rule that the Grasshopper client version moves only when it changes.
Standard library only (tests/ci runs with pytest alone)."""

import datetime
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    'release_prep', ROOT / 'scripts' / 'ci' / 'release_prep.py')
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)

LF = ('# Changelog\n\nintro\n\n## [0.6.3.1] - unreleased\n\n### Added\n\n- one thing\n\n'
      '## [0.6.3.0] - 2026-10-21\n\n### Added\n\n- older\n')
CRLF = LF.replace('\n', '\r\n')
TODAY = datetime.date(2026, 10, 22)


# THE SECTION -------------------------------------------------------------------
def test_the_section_of_a_version_is_found():
    body = rp.changelog_section(LF, '0.6.3.1')
    assert '- one thing' in body and '- older' not in body
    assert '- older' in rp.changelog_section(LF, '0.6.3.0')


def test_a_missing_section_is_none_and_counts_as_empty():
    assert rp.changelog_section(LF, '9.9.9.9') is None
    assert rp.section_is_empty(None)


def test_a_version_is_not_a_prefix_match():
    text = '## [0.6.3.10] - unreleased\n\n- x\n'
    assert rp.changelog_section(text, '0.6.3.1') is None


def test_a_section_with_only_headings_and_blanks_is_empty():
    assert rp.section_is_empty('\n\n### Added\n\n### Changed\n\n')
    assert rp.section_is_empty('')
    assert rp.section_is_empty('   \r\n\r\n')


def test_a_section_with_a_line_of_text_is_not_empty():
    assert not rp.section_is_empty('\n### Added\n\n- something\n')
    assert not rp.section_is_empty('A plain paragraph.\n')


def test_the_last_section_of_the_file_is_read_to_the_end():
    text = '## [1.0.0.0] - unreleased\n\n- last line without a newline'
    assert rp.changelog_section(text, '1.0.0.0').strip() == '- last line without a newline'


# THE DATE ----------------------------------------------------------------------
def test_unreleased_becomes_the_date():
    out, state = rp.set_changelog_date(LF, '0.6.3.1', '2026-10-22')
    assert state == 'dated'
    assert '## [0.6.3.1] - 2026-10-22\n' in out and 'unreleased' not in out
    assert out.replace('2026-10-22', 'unreleased', 1) == LF        # nothing else moved


def test_crlf_is_kept_exactly():
    out, state = rp.set_changelog_date(CRLF, '0.6.3.1', '2026-10-22')
    assert state == 'dated'
    assert out == CRLF.replace('unreleased', '2026-10-22')
    assert out.count('\r\n') == CRLF.count('\r\n') and '\n' not in out.replace('\r\n', '')


def test_only_the_heading_of_that_version_changes():
    text = LF + '\n## [0.6.2.0] - unreleased\n\n- an old unreleased heading\n'
    out, _ = rp.set_changelog_date(text, '0.6.3.1', '2026-10-22')
    assert '## [0.6.2.0] - unreleased' in out


def test_a_second_run_changes_nothing_and_says_so():
    once, _ = rp.set_changelog_date(LF, '0.6.3.1', '2026-10-22')
    twice, state = rp.set_changelog_date(once, '0.6.3.1', '2026-10-22')
    assert state == 'already' and twice == once


def test_a_date_that_is_set_is_not_overwritten_by_another_one():
    once, _ = rp.set_changelog_date(LF, '0.6.3.1', '2026-10-22')
    again, state = rp.set_changelog_date(once, '0.6.3.1', '2026-11-30')
    assert state == 'already' and again == once
    assert rp.existing_date(again, '0.6.3.1') == '2026-10-22'


def test_a_missing_section_or_a_heading_without_unreleased_is_reported():
    assert rp.set_changelog_date(LF, '9.9.9.9', '2026-10-22')[1] == 'missing'
    odd = '## [0.6.3.1] - soon\n\n- x\n'
    assert rp.set_changelog_date(odd, '0.6.3.1', '2026-10-22') == (odd, 'missing')


def test_a_date_that_is_not_a_date_is_refused():
    for bad in ('2026-13-01', '22.10.2026', 'today', '2026-10-32'):
        with pytest.raises(ValueError):
            rp.set_changelog_date(LF, '0.6.3.1', bad)


def test_a_date_has_to_be_there_for_existing_date():
    assert rp.existing_date(LF, '0.6.3.1') is None
    assert rp.existing_date(LF, '0.6.3.0') == '2026-10-21'
    assert rp.existing_date(LF, '1.2.3.4') is None


# THE GRASSHOPPER CLIENT ---------------------------------------------------------
SESSION = ('"""\r\nDDU_CSC_Session\r\nVersion: 261020\r\n"""\r\n'
           "CSC_CLIENT = 'gh-userobjects/0.6.3.0'\r\nCSC_GH_MINIMUM = '261020'\r\n")


def test_an_equal_client_version_changes_nothing_at_all():
    out, changed = rp.gh_client_update(SESSION, '0.6.3.0', TODAY)
    assert changed is False and out == SESSION           # the header date stays


def test_a_new_client_version_rewrites_the_client_and_the_header_date():
    out, changed = rp.gh_client_update(SESSION, '0.6.3.1', TODAY)
    assert changed is True
    assert "CSC_CLIENT = 'gh-userobjects/0.6.3.1'" in out
    assert 'Version: 261022' in out and 'Version: 261020' not in out
    assert "CSC_GH_MINIMUM = '261020'" in out            # the minimum is its own
    assert out.count('\r\n') == SESSION.count('\r\n')
    assert out.replace('0.6.3.1', '0.6.3.0').replace('261022', '261020') == SESSION


def test_a_prerelease_version_is_a_different_version():
    out, changed = rp.gh_client_update(SESSION, '0.6.3.0-beta.1', TODAY)
    assert changed and "gh-userobjects/0.6.3.0-beta.1" in out


def test_the_rule_applies_again_after_the_change():
    first, changed = rp.gh_client_update(SESSION, '0.6.3.1', TODAY)
    again, changed_again = rp.gh_client_update(first, '0.6.3.1', datetime.date(2027, 1, 1))
    assert changed and not changed_again and again == first


def test_a_source_without_the_lines_is_an_error():
    with pytest.raises(ValueError):
        rp.gh_client_update('no client here\r\n', '0.6.3.1', TODAY)
    with pytest.raises(ValueError):
        rp.gh_client_update("CSC_CLIENT = 'gh-userobjects/0.6.3.0'\r\n", '0.6.3.1', TODAY)
    # an equal version needs no header
    out, changed = rp.gh_client_update("CSC_CLIENT = 'gh-userobjects/0.6.3.1'\r\n", '0.6.3.1', TODAY)
    assert changed is False


# THE NEXT STEPS NAME THEIR FILES (0.6.3.1) -------------------------------------
def test_the_next_steps_name_the_files_and_never_add_everything():
    text = rp.next_steps('0.6.3.1')
    assert 'git add -A' not in text and 'git add .' not in text
    for name in ('CHANGELOG.md', '.zenodo.json', 'VERSION', 'src/backend/csc_version.py',
                 'src/frontend/package.json', 'src/frontend/package-lock.json', 'README.md'):
        assert name in text, name
    assert 'git tag v0.6.3.1 && git push origin v0.6.3.1' in text
    assert 'DDU_CSC_Session.py' in text                 # the --gh case is mentioned


def test_every_named_file_exists_in_the_repository():
    for name in rp.RELEASE_FILES + rp.GH_RELEASE_FILES:
        assert (ROOT / name).is_file(), name


def test_the_named_files_are_the_ones_bump_version_writes():
    """bump-version rewrites exactly these (tasks.py): a file added there has
    to be named here."""
    source = (ROOT / 'tasks.py').read_text(encoding='utf-8')
    for needle in ("'VERSION'", "'csc_version.py'", "'package.json'", "'package-lock.json'",
                   "'README.md'", "'CHANGELOG.md'", "'DDU_CSC_Session.py'"):
        assert needle in source, needle
    assert '.zenodo.json' in ' '.join(rp.RELEASE_FILES)
