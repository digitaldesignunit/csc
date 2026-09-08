"""CLI and selection helpers for descriptor computation."""

from __future__ import annotations

import pytest

from apps.descriptors.registry import applicable_specs_for, missing_specs_for
from apps.descriptors.specs import ALL_SPECS, BOXSCORE, RADIAL_SIGNATURE
from main_descriptors_simple import (
    _max_iterations,
    _parse_args,
    run_specs_on_snapshot,
)


def test_default_is_cron_mode_one_snapshot():
    args = _parse_args([])
    assert not args.recompute
    assert not args.process_all
    assert _max_iterations(args) == 1


def test_recompute_walks_every_snapshot_unless_limited():
    args = _parse_args(['--recompute'])
    assert args.recompute
    assert _max_iterations(args) is None
    args = _parse_args(['--recompute', '--limit', '4'])
    assert _max_iterations(args) == 4


def test_recompute_cannot_combine_with_all():
    with pytest.raises(SystemExit):
        _parse_args(['--recompute', '--all'])


def test_all_and_limit_can_cap_a_missing_backfill():
    args = _parse_args(['--all', '--limit', '7'])
    assert args.process_all
    assert _max_iterations(args) == 7


def test_limit_must_be_positive(capsys):
    with pytest.raises(SystemExit) as exc:
        _max_iterations(_parse_args(['--limit', '0']))
    assert exc.value.code == 2
    assert 'positive' in capsys.readouterr().err


def test_applicable_specs_include_already_computed_keys():
    component = {
        'type': 'panel',
        'geometry': {'extrusions': [{'profile': [[0, 0], [1, 0], [1, 1]],
                                     'height': 2.0}]},
        'descriptors': {'boxscore': 0.1, 'radial_distance_64': [1.0] * 64},
    }
    applicable = applicable_specs_for(component, ALL_SPECS)
    missing = missing_specs_for(component, ALL_SPECS)
    assert BOXSCORE in applicable
    assert RADIAL_SIGNATURE in applicable
    assert BOXSCORE not in missing


def test_recompute_runs_specs_that_are_already_stored():
    component = {
        'type': 'brick',
        'geometry': {
            'meshes': [{
                'v': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
                'f': [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]],
            }],
        },
        'descriptors': {'boxscore': 99.0},
    }
    missing = run_specs_on_snapshot(component, None, [BOXSCORE])
    assert missing == {}
    recomputed = run_specs_on_snapshot(
        component, None, [BOXSCORE], recompute=True)
    assert 'boxscore' in recomputed
    assert recomputed['boxscore'] != 99.0
