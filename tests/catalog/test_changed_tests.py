"""``invoke test-changed``: which tests belong to which changed paths
(decision 8.114)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'dev'))

from changed_tests import plan  # noqa: E402


def _plan(*paths, existing=()):
    return plan(paths, exists=lambda p: p in existing)


def test_backend_api_maps_to_the_route_tests_only():
    result = _plan('src/backend/apps/catalog/api/identity_edit.py')
    assert result.pytest_targets == ['tests/api'] and not result.frontend


def test_other_backend_code_maps_to_catalog_and_api():
    result = _plan('src/backend/apps/catalog/lineage.py')
    assert result.pytest_targets == ['tests/api', 'tests/catalog']


def test_grasshopper_sources_map_to_the_grasshopper_tests():
    result = _plan('grasshopper_lib/csc_gh/build.py',
                   'grasshopper_userobjects_src/CSC_Update.py')
    assert result.pytest_targets == ['tests/grasshopper']


def test_a_changed_test_is_itself_and_a_helper_means_its_folder():
    result = _plan('tests/api/test_a.py', 'tests/api/test_gone.py',
                   'tests/catalog/examples06.py', 'tests/catalog/test_b.py',
                   existing=('tests/api/test_a.py', 'tests/catalog/test_b.py'))
    # test_b.py is covered by its folder, the deleted test runs nothing
    assert result.pytest_targets == ['tests/api/test_a.py', 'tests/catalog']


def test_a_folder_covers_the_files_inside_it():
    result = _plan('src/backend/apps/catalog/api/x.py', 'tests/api/test_a.py',
                   existing=('tests/api/test_a.py',))
    assert result.pytest_targets == ['tests/api']


def test_frontend_changes_run_lint_tsc_and_the_test_next_to_a_lib_file():
    result = _plan('src/frontend/lib/lineage.ts', 'src/frontend/lib/other.ts',
                   'src/frontend/components/x.tsx',
                   existing=('src/frontend/lib/lineage.test.ts',))
    assert result.frontend and not result.pytest_targets
    assert result.frontend_tests == ['lib/lineage.test.ts']


def test_nothing_that_maps_is_empty():
    assert _plan('docs/adr/DESIGN_DECISIONS.md', 'README.md').empty
    assert not _plan('pytest.ini').empty
