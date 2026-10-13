"""
S11 (decision 8.144): trimesh 5 or newer, and no mesh is loaded with its
materials; the web stack and the PDF library are pinned to what the backend is
tested with.
"""

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / 'src' / 'backend'
REQUIREMENTS = (BACKEND / 'requirements.txt').read_text(encoding='utf-8')
CONSTRAINTS = (BACKEND / 'constraints.txt').read_text(encoding='utf-8')
PINNED = ('fastapi', 'starlette', 'uvicorn', 'gunicorn', 'reportlab')


def test_trimesh_5_or_newer_is_required():
    assert re.search(r'^trimesh>=5$', REQUIREMENTS, re.M)
    assert int(metadata.version('trimesh').split('.')[0]) >= 5


def test_every_trimesh_load_of_the_backend_skips_materials():
    loads = []
    for path in (BACKEND / 'apps').rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        for match in re.finditer(r'trimesh\.load\(([^)]*)\)', text):
            loads.append((path.name, match.group(1)))
    assert len(loads) >= 5
    for name, call in loads:
        assert 'skip_materials=True' in call, (name, call)


def test_a_mesh_loads_with_skip_materials(tmp_path):
    import trimesh
    path = tmp_path / 'box.ply'
    path.write_bytes(trimesh.creation.box().export(file_type='ply'))
    from apps.catalog.geometry_mesh_export import load_trimesh_from_ply_file
    assert len(load_trimesh_from_ply_file(str(path)).faces) == 12


@pytest.mark.parametrize('name', PINNED)
def test_the_web_stack_and_reportlab_are_pinned_to_the_installed_version(name):
    match = re.search(rf'^{name}==(\S+)$', CONSTRAINTS, re.M)
    assert match, f'{name} is not pinned in constraints.txt'
    assert metadata.version(name) == match.group(1)
