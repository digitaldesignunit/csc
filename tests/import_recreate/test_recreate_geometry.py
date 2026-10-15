"""geometry.py: one watertight mesh per product, from hand-written view polygons (decision 8.145).
Needs numpy, manifold3d, trimesh and shapely (requirements-import.txt); skipped without them."""

from __future__ import annotations

import math

import pytest

L, T, H = 4000.0, 200.0, 2500.0                    # length (x), thickness (y), height (z), mm
WALL_M3 = L * T * H / 1e9


def views(front=None, side=None, plan=None, **extra):
    """A wall's three views as the header keys the parser produces (columns as lists)."""
    front = front or [(0, 0), (L, 0), (L, H), (0, H)]
    side = side or [(0, 0), (T, 0), (T, H), (0, H)]
    plan = plan or [(0, 0), (L, 0), (L, T), (0, T)]
    rec = {
        'GENERAL / FRONT CROSS-SECTION [list] / X []': [p[0] for p in front],
        'GENERAL / FRONT CROSS-SECTION [list] / Z []': [p[1] for p in front],
        'GENERAL / SIDE CROSS-SECTION [list] / Y []': [p[0] for p in side],
        'GENERAL / SIDE CROSS-SECTION [list] / Z []': [p[1] for p in side],
        'GENERAL / PLAN CROSS-SECTION [list] / X []': [p[0] for p in plan],
        'GENERAL / PLAN CROSS-SECTION [list] / Y []': [p[1] for p in plan],
    }
    rec.update(extra)
    return rec


def void_corners(x0, x1, z0, z1, y0=0.0, y1=T):
    """The 8 corners of one void (front and back face), as the Void Corners columns."""
    pts = [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
           (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]
    return {'WALL VOIDS / Count': 1,
            'WALL VOIDS / Void Corners [list] / X []': [p[0] for p in pts],
            'WALL VOIDS / Void Corners [list] / Y []': [p[1] for p in pts],
            'WALL VOIDS / Void Corners [list] / Z []': [p[2] for p in pts]}


def mesh_of(geometry_module, solid):
    return geometry_module.to_trimesh(solid)


def wall(geometry_module, rec):
    notes = []
    solid = geometry_module.element_solid(rec, notes)
    return mesh_of(geometry_module, solid), notes


# A BOX FROM THREE VIEWS ------------------------------------------------------
def test_a_box_from_three_views(geometry_module):
    mesh, notes = wall(geometry_module, views())
    assert mesh.is_watertight
    assert mesh.volume / 1e9 == pytest.approx(WALL_M3, rel=1e-6)
    lo, hi = mesh.bounds
    assert list(lo) == pytest.approx([0, 0, 0]) and list(hi) == pytest.approx([L, T, H])
    assert notes == []


def test_the_views_are_intersected_so_a_tapered_front_cuts_the_box(geometry_module):
    # the front view is a trapezoid: the plan and side views alone would give the full box
    front = [(0, 0), (L, 0), (L - 1000, H), (1000, H)]
    mesh, _ = wall(geometry_module, views(front=front))
    trapezoid = (L + (L - 2000)) / 2 * H * T / 1e9
    assert mesh.is_watertight and mesh.volume / 1e9 == pytest.approx(trapezoid, rel=1e-6)


def test_two_views_are_enough_and_one_is_not(geometry_module):
    rec = views()
    del rec['GENERAL / PLAN CROSS-SECTION [list] / X []'], rec['GENERAL / PLAN CROSS-SECTION [list] / Y []']
    mesh, _ = wall(geometry_module, rec)
    assert mesh.volume / 1e9 == pytest.approx(WALL_M3, rel=1e-6)
    only_front = {k: v for k, v in views().items() if 'FRONT' in k}
    with pytest.raises(ValueError, match='fewer than two views'):
        geometry_module.element_solid(only_front, [])


# VOIDS -----------------------------------------------------------------------
def test_a_void_changes_the_volume_by_the_void(geometry_module):
    full, _ = wall(geometry_module, views())
    window = void_corners(1000, 2000, 500, 1500)
    cut, notes = wall(geometry_module, views(**window))
    void_m3 = 1000 * 1000 * T / 1e9
    assert cut.is_watertight
    assert full.volume / 1e9 - cut.volume / 1e9 == pytest.approx(void_m3, rel=1e-6)
    assert not cut.contains([[1500, T / 2, 1000]])[0]               # in the window: empty
    assert cut.contains([[3000, T / 2, 1000]])[0]                   # beside it: concrete
    assert notes == []


def test_a_declared_void_count_that_disagrees_is_noted(geometry_module):
    rec = views(**void_corners(1000, 2000, 500, 1500))
    rec['WALL VOIDS / Count'] = 2
    _, notes = wall(geometry_module, rec)
    assert any('void count 2, corner sets 1' in n for n in notes)


def test_corners_that_are_not_a_multiple_of_eight_skip_the_void_and_say_so(geometry_module):
    rec = views(**void_corners(1000, 2000, 500, 1500))
    for key in [k for k in rec if k.startswith('WALL VOIDS / Void Corners')]:
        rec[key] = rec[key][:7]
    mesh, notes = wall(geometry_module, rec)
    assert mesh.volume / 1e9 == pytest.approx(WALL_M3, rel=1e-6)
    assert any('not a multiple of 8' in n for n in notes)


# SWAPPED PLAN AXES ---------------------------------------------------------------
def test_a_plan_view_with_swapped_axes_is_detected_and_swapped_back(geometry_module):
    swapped = [(0, 0), (T, 0), (T, L), (0, L)]                      # x 0..200, y 0..4000: the wrong way
    mesh, notes = wall(geometry_module, views(plan=swapped))
    assert mesh.is_watertight and mesh.volume / 1e9 == pytest.approx(WALL_M3, rel=1e-6)
    assert any('view entered with its axes swapped; swapped back' in n for n in notes)


def test_a_correct_plan_view_is_left_alone(geometry_module):
    _, notes = wall(geometry_module, views())
    assert not any('swapped' in n for n in notes)


# MIRRORING ------------------------------------------------------------------
def test_a_mirrored_product_is_reflected_about_the_middle_of_its_length(geometry_module):
    window = void_corners(500, 1000, 500, 1500)                    # near the x = 0 end
    plain, _ = wall(geometry_module, views(**window))
    mirrored, notes = wall(geometry_module, views(**window, **{'Mirrored': True}))
    assert mirrored.is_watertight
    assert mirrored.volume == pytest.approx(plain.volume, rel=1e-9)
    inside_window = [[750, T / 2, 1000]]
    assert not plain.contains(inside_window)[0] and mirrored.contains(inside_window)[0]
    reflected = [[L - 750, T / 2, 1000]]                           # x -> L - x
    assert plain.contains(reflected)[0] and not mirrored.contains(reflected)[0]
    assert 'mirrored about x = L / 2' in notes
    lo, hi = mirrored.bounds
    assert list(lo) == pytest.approx([0, 0, 0]) and list(hi) == pytest.approx([L, T, H])


# HOLLOW-CORE SLABS --------------------------------------------------------------
def hcs(width=1200.0, length=6000.0, height=200.0, cores=4, dx=180.0, dz=100.0, bottom=50.0, web=30.0,
        topping=None):
    rec = {'GEOMETRY / Height (mm)': height, 'GEOMETRY / Length (mm)': length, 'GEOMETRY / Width (mm)': width,
           'GEOMETRY / Voids / Count': cores, 'GEOMETRY / Voids / Diameter X (mm)': dx,
           'GEOMETRY / Voids / Diameter Y (mm)': dz, 'GEOMETRY / Voids / Bottom Cover (mm)': bottom,
           'GEOMETRY / Voids / Web Thickness [External] (mm)': web}
    if topping:
        rec['STRUCTURAL TOPPING / Present [boolean]'] = True
        rec['STRUCTURAL TOPPING / Thickness (mm)'] = topping
    return rec


def test_the_cores_of_a_hollow_core_slab_are_cut_along_its_length(geometry_module):
    notes = []
    mesh = mesh_of(geometry_module, geometry_module.hcs_solid(hcs(), notes))
    box = 6000.0 * 1200.0 * 200.0
    # an inscribed 48-gon for the ellipse: area = n / 2 sin(2 pi / n) a b
    cores = 4 * 0.5 * 48 * math.sin(2 * math.pi / 48) * (180.0 / 2) * (100.0 / 2) * 6000.0
    assert mesh.is_watertight
    assert mesh.volume == pytest.approx(box - cores, rel=1e-4)
    # a point inside the first core is empty, one in the first web is concrete
    first_core_y = 30.0 + 180.0 / 2
    assert not mesh.contains([[3000, first_core_y, 50 + 100 / 2]])[0]
    assert mesh.contains([[3000, 15, 100]])[0]
    assert notes == []


def test_cores_that_do_not_fit_the_width_are_skipped_and_noted(geometry_module):
    notes = []
    mesh = mesh_of(geometry_module, geometry_module.hcs_solid(hcs(width=700.0), notes))
    assert mesh.is_watertight
    assert mesh.volume == pytest.approx(6000.0 * 700.0 * 200.0, rel=1e-9)     # the full box
    assert any('cores do not fit the width' in n and 'cores skipped' in n for n in notes)


def test_a_structural_topping_adds_its_thickness_to_the_height(geometry_module):
    notes = []
    mesh = mesh_of(geometry_module, geometry_module.hcs_solid(hcs(topping=50.0), notes))
    lo, hi = mesh.bounds
    assert hi[2] - lo[2] == pytest.approx(250.0)
    assert mesh.is_watertight
    assert 'structural topping 50 mm' in notes


def test_a_cut_slab_spreads_its_cores_evenly_and_says_so(geometry_module):
    notes = []
    mesh = mesh_of(geometry_module, geometry_module.hcs_solid(hcs(width=700.0, cores=3), notes))
    assert mesh.is_watertight
    assert any('cut width 700 mm: cores spread evenly' in n for n in notes)


# EVERY RESULT IS WATERTIGHT -------------------------------------------------------
def test_every_kind_of_result_is_watertight(geometry_module):
    corbel = {'CORBEL GEOMETRY / Count': 1,
              'CORBEL GEOMETRY / FRONT VIEW [list] / X []': [0, 400, 400, 0],
              'CORBEL GEOMETRY / FRONT VIEW [list] / Z []': [0, 0, 300, 300],
              'CORBEL GEOMETRY / SIDE VIEW [list] / Y []': [-100, T, T, -100],
              'CORBEL GEOMETRY / SIDE VIEW [list] / Z []': [0, 0, 300, 300]}
    cases = [wall(geometry_module, views())[0],
             wall(geometry_module, views(**void_corners(1000, 2000, 500, 1500)))[0],
             wall(geometry_module, views(plan=[(0, 0), (T, 0), (T, L), (0, L)]))[0],
             wall(geometry_module, views(**{'Mirrored': True}))[0],
             wall(geometry_module, views(**corbel))[0],
             mesh_of(geometry_module, geometry_module.hcs_solid(hcs(), [])),
             mesh_of(geometry_module, geometry_module.hcs_solid(hcs(topping=40.0), []))]
    for mesh in cases:
        assert mesh.is_watertight and mesh.volume > 0


def test_a_corbel_is_added_to_the_wall(geometry_module):
    corbel = {'CORBEL GEOMETRY / Count': 1,
              'CORBEL GEOMETRY / FRONT VIEW [list] / X []': [0, 400, 400, 0],
              'CORBEL GEOMETRY / FRONT VIEW [list] / Z []': [0, 0, 300, 300],
              'CORBEL GEOMETRY / SIDE VIEW [list] / Y []': [-100, T, T, -100],
              'CORBEL GEOMETRY / SIDE VIEW [list] / Z []': [0, 0, 300, 300]}
    plain, _ = wall(geometry_module, views())
    with_corbel, notes = wall(geometry_module, views(**corbel))
    assert with_corbel.volume > plain.volume
    assert with_corbel.bounds[0][1] == pytest.approx(-100.0)         # it sticks out of the wall's face
    assert not any('skipped' in n for n in notes)


def test_a_radius_is_reported_and_ignored(geometry_module):
    rec = views(**{'GENERAL / FRONT CROSS-SECTION [list] / Radius/ Bevel (mm) []': [0, 25, 0, 0],
                   'GENERAL / PLAN CROSS-SECTION [list] / Radius (mm) []': [0, 0, 0, 0]})
    mesh, notes = wall(geometry_module, rec)
    assert mesh.volume / 1e9 == pytest.approx(WALL_M3, rel=1e-6)
    assert 'element: radius / bevel given and ignored' in notes


def test_both_radius_spellings_are_recognised_but_all_zero_is_silent(geometry_module):
    for key in ('GENERAL / FRONT CROSS-SECTION [list] / Radius/ Bevel (mm) []',
                'GENERAL / FRONT CROSS-SECTION [list] / Radius (mm) []'):
        _, notes = wall(geometry_module, views(**{key: [0, 0, 0, 0]}))
        assert not any('radius' in n for n in notes), key
        _, notes = wall(geometry_module, views(**{key: [0, 10, 0, 0]}))
        assert any('radius' in n for n in notes), key
