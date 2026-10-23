"""Vertex colours from a texture (8.175): the pure sampling, outside Rhino."""

from __future__ import annotations

import numpy as np
import pytest

from csc_gh import texture as t

# a 4 x 2 image: the top row (image row 0) red, green, blue, white; the bottom
# row black, cyan, magenta, yellow
IMAGE = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]],
                  [[0, 0, 0], [0, 255, 255], [255, 0, 255], [255, 255, 0]]],
                 dtype=np.uint8)


def _at(u, v, **kwargs):
    return t.sample_bilinear(IMAGE, [[u, v]], **kwargs)[0].tolist()


def test_a_coordinate_on_a_pixel_centre_returns_that_pixel():
    # centre of pixel (i, j): u = (i + .5) / 4, and v = 1 - (j + .5) / 2
    for j in range(2):
        for i in range(4):
            assert _at((i + 0.5) / 4, 1 - (j + 0.5) / 2) == IMAGE[j, i].tolist()


def test_v_runs_from_the_bottom_and_image_row_0_is_the_top():
    assert _at(0.125, 0.75) == [255, 0, 0]        # top left: red
    assert _at(0.125, 0.25) == [0, 0, 0]          # bottom left: black
    assert _at(0.875, 0.75) == [255, 255, 255]    # top right
    assert _at(0.875, 0.25) == [255, 255, 0]      # bottom right


def test_between_centres_the_four_neighbours_are_blended_as_stored():
    # half way between red (0,0) and green (1,0) along the top row
    assert _at(0.25, 0.75) == [128, 128, 0]       # 127.5 rounds to 128, as stored: no gamma
    # the middle of the four pixels (0,0) (1,0) (0,1) (1,1): red, green, black, cyan
    assert _at(0.25, 0.5) == [64, 128, 64]
    # a quarter of the way: 3 : 1 towards the nearer one
    assert _at(0.1875, 0.75) == [191, 64, 0]


def test_outside_the_image_the_texture_repeats_by_default():
    assert _at(1.125, 0.75) == _at(0.125, 0.75) == [255, 0, 0]
    assert _at(-0.875, 0.75) == [255, 0, 0]
    assert _at(0.125, 1.75) == _at(0.125, 0.75)
    assert _at(0.125, -0.25) == _at(0.125, 0.75) == [255, 0, 0]
    # the seam: u = 1 blends the last and the first column
    assert _at(1.0, 0.75) == [255, 128, 128]      # (white + red) / 2


def test_clamp_holds_the_edge_pixels_instead():
    clamp = {'wrap_u': t.WRAP_CLAMP, 'wrap_v': t.WRAP_CLAMP}
    assert _at(1.5, 0.75, **clamp) == [255, 255, 255]
    assert _at(-3.0, 0.75, **clamp) == [255, 0, 0]
    assert _at(0.125, 5.0, **clamp) == [255, 0, 0]     # above the top: the top row
    assert _at(0.125, -5.0, **clamp) == [0, 0, 0]
    assert _at(1.0, 0.75, **clamp) == [255, 255, 255]  # no blend with the far edge
    # u and v wrap on their own
    mixed = {'wrap_u': t.WRAP_CLAMP, 'wrap_v': t.WRAP_REPEAT}
    assert _at(1.5, 1.75, **mixed) == [255, 255, 255]


def test_the_channel_order_of_a_dotnet_bitmap_is_bgra():
    bgra = np.zeros((1, 2, 4), dtype=np.uint8)
    bgra[0, 0] = (10, 20, 30, 255)        # B, G, R, A in memory: red 30
    bgra[0, 1] = (40, 50, 60, 255)
    got = t.sample_bilinear(bgra, [[0.25, 0.5], [0.75, 0.5]], rgb=(2, 1, 0))
    assert got.tolist() == [[30, 20, 10], [60, 50, 40]]


def test_many_points_at_once_keep_their_order_and_the_dtype():
    rng = np.random.default_rng(1)
    uv = rng.uniform(-2, 3, (5000, 2))
    got = t.sample_bilinear(IMAGE, uv)
    assert got.shape == (5000, 3) and got.dtype == np.uint8
    one = np.array([t.sample_bilinear(IMAGE, uv[i:i + 1])[0] for i in (0, 17, 4999)])
    assert np.array_equal(got[[0, 17, 4999]], one)


def test_a_constant_image_gives_that_colour_everywhere():
    flat = np.full((7, 5, 3), (12, 200, 99), dtype=np.uint8)
    got = t.sample_bilinear(flat, np.random.default_rng(2).uniform(-5, 5, (300, 2)))
    assert (got == (12, 200, 99)).all()


def test_a_coordinate_that_is_not_a_number_is_taken_as_0():
    got = t.sample_bilinear(IMAGE, [[np.nan, np.inf], [0.125, 0.75]])
    assert got[1].tolist() == [255, 0, 0] and got[0].shape == (3,)
    assert t.sample_bilinear(IMAGE, np.zeros((0, 2))).shape == (0, 3)


def test_an_image_that_is_not_height_width_colour_is_refused():
    for bad in (np.zeros((4, 4)), np.zeros((0, 4, 3)), np.zeros((2, 2, 2))):
        with pytest.raises(ValueError):
            t.sample_bilinear(bad, [[0, 0]])


def test_the_pixel_position_flips_v_and_centres_the_texels():
    x, y = t.pixel_position([[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]], 10, 20)
    assert x.tolist() == [-0.5, 9.5, 4.5] and y.tolist() == [-0.5, 19.5, 9.5]


def test_the_wrap_names_are_rhinos():
    assert t.wrap_of('Clamp') == t.WRAP_CLAMP and t.wrap_of(' clamp ') == t.WRAP_CLAMP
    assert t.wrap_of('Repeat') == t.WRAP_REPEAT and t.wrap_of('Mirror') == t.WRAP_REPEAT
    assert t.wrap_of(None) == t.WRAP_REPEAT


def test_which_materials_the_meshs_own_coordinates_can_express():
    ok = dict(enabled=True, channel=1, transform_identity=True, texture_coordinates=50, vertices=50)
    assert t.texture_problem(**ok) is None
    assert 'switched off' in t.texture_problem(**dict(ok, enabled=False))
    assert 'no texture coordinates' in t.texture_problem(**dict(ok, texture_coordinates=0))
    assert 'no texture coordinates' in t.texture_problem(**dict(ok, texture_coordinates=49))
    assert 'no texture coordinates' in t.texture_problem(**dict(ok, vertices=0, texture_coordinates=0))
    assert 'mapping channel 2' in t.texture_problem(**dict(ok, channel=2))
    assert 'transform' in t.texture_problem(**dict(ok, transform_identity=False))


def test_a_huge_image_is_not_read():
    assert not t.too_large(8192, 8192)
    assert t.too_large(20000, 20000)


def test_a_texture_transform_that_leaves_u_and_v_alone_is_no_transform():
    identity = np.eye(4)
    assert t.uv_transform_is_identity(identity)
    # a render material's texture: the w part is 0 instead of 1
    render = np.eye(4)
    render[2, 2] = 0.0
    assert t.uv_transform_is_identity(render)
    for change in ((0, 0, 2.0), (1, 1, 0.5), (0, 1, 0.1), (1, 0, -0.1), (0, 3, 0.25), (1, 3, -1.0)):
        moved = np.eye(4)
        moved[change[0], change[1]] = change[2]
        assert not t.uv_transform_is_identity(moved), change
    flipped = np.eye(4)
    flipped[1, 1] = -1.0
    assert not t.uv_transform_is_identity(flipped)
    # tiny rounding noise is no transform
    assert t.uv_transform_is_identity(np.eye(4) + 1e-12)
