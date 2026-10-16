"""Tests of the ReCreate import tools (scripts/import/recreate, decision 8.145).

The fixtures are rows written by hand, never the Zenodo files. Only what a plain environment has is needed
for the planner, the fetch step and the shared helpers; the tests that need openpyxl, manifold3d, trimesh
or shapely skip themselves where those are not installed (``requirements-import.txt``). CI does not run
this folder (decision 8.114): it runs locally.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts' / 'import' / 'recreate'


def load_script(name: str):
    """A script of the tool folder as a module of its own name (``recreate_<name>``): the folder has
    generic file names (``parse``, ``plan``, ``run``) that must not clash with anything else."""
    module_name = f'recreate_{name}'
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_common():
    """The shared helpers (``recreate_common``), imported the way the scripts import them."""
    sys.path.insert(0, str(SCRIPTS))
    import recreate_common
    return recreate_common


@pytest.fixture(scope='session')
def script_loader():
    return load_script


@pytest.fixture(scope='session')
def common():
    return load_common()


@pytest.fixture(scope='session')
def plan_module():
    return load_script('plan')


@pytest.fixture(scope='session')
def fetch_module():
    return load_script('fetch')


@pytest.fixture(scope='session')
def parse_module():
    pytest.importorskip('openpyxl')
    return load_script('parse')


@pytest.fixture(scope='session')
def geometry_module():
    for name in ('numpy', 'manifold3d', 'trimesh', 'shapely'):
        pytest.importorskip(name)
    return load_script('geometry')
