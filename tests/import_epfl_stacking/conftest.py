"""Tests of the EPFL stone import tools (scripts/import/epfl_stacking, decision 8.146).

Fixtures are tiny PLY files and records made here, never the dataset. What needs numpy, scipy, trimesh or
fast-simplification skips itself where those are not installed (``scripts/import/requirements-import.txt``).
CI does not run this folder (decision 8.114): it runs locally.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts' / 'import' / 'epfl_stacking'


def load_script(name: str):
    """A script of the tool folder as a module of its own name (``epfl_<name>``): the folder has generic file
    names (``fetch``, ``plan``, ``run``) that must not clash with the ReCreate scripts or anything else."""
    module_name = f'epfl_{name}'
    if module_name in sys.modules:
        return sys.modules[module_name]
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def need(*names):
    for name in names:
        pytest.importorskip(name)


@pytest.fixture(scope='session')
def script_loader():
    return load_script


@pytest.fixture(scope='session')
def epfl():
    sys.path.insert(0, str(SCRIPTS))
    import epfl_common
    return epfl_common


@pytest.fixture(scope='session')
def fetch_module():
    return load_script('fetch')


@pytest.fixture(scope='session')
def plan_module():
    return load_script('plan')


@pytest.fixture(scope='session')
def prepare_module():
    need('numpy', 'scipy', 'trimesh', 'fast_simplification')
    return load_script('prepare')
