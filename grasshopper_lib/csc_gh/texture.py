# Vertex colours from a texture (decision 8.175): the pure part.
#
# A textured scan keeps its look when CreateComponentIdentity / Snapshot stage
# it: each vertex takes the colour of the texture image at its texture
# coordinate. This module holds the numbers only (no Rhino, numpy): the
# coordinate to pixel conversion with the flipped V axis, wrap or clamp, the
# bilinear sampling, and the decision which materials the mesh's own texture
# coordinates can express. Reading the image and the material out of Rhino is
# in ``rhino.py``.
#
# Conventions (all of them decided here, tested in tests/grasshopper):
#
# * ``u`` runs along the image from its left edge (0) to its right edge (1);
#   ``v`` runs from the BOTTOM (0) to the TOP (1) of the image, while image
#   row 0 is the TOP row: row = (1 - v) * height.
# * Texel centres sit at half-integers: the pixel (i, j) is the colour at
#   u = (i + 0.5) / width, so a coordinate on a centre returns that pixel
#   exactly and between centres the four neighbours are blended.
# * Outside 0..1 the texture repeats (Rhino's default, ``Repeat``) or clamps to
#   the edge pixels when the material says ``Clamp``.
# * Colours are blended as stored (sRGB values, no linearisation) and rounded
#   to the nearest 8-bit value. The alpha channel is ignored.
#
# Python 3.9 compatible; part of the package csc_gh (decision 8.111).

import numpy as np  # NOQA

WRAP_REPEAT = 'repeat'
WRAP_CLAMP = 'clamp'
WRAPS = (WRAP_REPEAT, WRAP_CLAMP)

# the most pixels of a texture that is read (about 10 000 x 10 000)
MAX_PIXELS = 100_000_000


def wrap_of(name):
    """``'repeat'`` or ``'clamp'`` from the name Rhino gives its wrapping
    (``Repeat`` / ``Clamp``); anything else repeats, Rhino's default."""
    return WRAP_CLAMP if str(name).strip().lower() == WRAP_CLAMP \
        else WRAP_REPEAT


def pixel_position(uv, width, height):
    """The continuous pixel position ``(x, y)`` of texture coordinates
    ``uv`` (n, 2): ``x = u * width - 0.5`` and ``y = (1 - v) * height - 0.5``,
    so a pixel centre is an integer position and image row 0 is the top (the V
    flip). A coordinate that is not a number is taken as 0."""
    uv = np.nan_to_num(np.asarray(uv, dtype=np.float64).reshape(-1, 2),
                       nan=0.0, posinf=0.0, neginf=0.0)
    x = uv[:, 0] * width - 0.5
    y = (1.0 - uv[:, 1]) * height - 0.5
    return x, y


def wrap_index(index, size, mode):
    """Integer pixel indices inside ``0..size-1``: modulo ``size`` for
    ``repeat``, clipped to the edge for ``clamp``."""
    index = np.asarray(index, dtype=np.int64)
    if mode == WRAP_CLAMP:
        return np.clip(index, 0, size - 1)
    return np.mod(index, size)


def sample_bilinear(image, uv, wrap_u=WRAP_REPEAT, wrap_v=WRAP_REPEAT,
                    rgb=(0, 1, 2)):
    """Bilinear colours ``(n, 3) uint8`` of ``image`` (height, width, >= 3
    channels, uint8) at texture coordinates ``uv`` (n, 2). ``rgb`` names the
    channels holding red, green and blue (``(2, 1, 0)`` for the BGRA memory
    of a .NET bitmap). Nothing per pixel is looped in Python."""
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] < 3 or not image.shape[0] \
            or not image.shape[1]:
        raise ValueError('the image needs height x width x 3 or more')
    height, width = image.shape[:2]
    x, y = pixel_position(uv, width, height)
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]
    ix0 = wrap_index(x0, width, wrap_u)
    ix1 = wrap_index(x0 + 1, width, wrap_u)
    iy0 = wrap_index(y0, height, wrap_v)
    iy1 = wrap_index(y0 + 1, height, wrap_v)
    channels = list(rgb)
    out = np.zeros((len(ix0), 3), dtype=np.float64)
    for ix, iy, weight in ((ix0, iy0, (1 - fx) * (1 - fy)),
                           (ix1, iy0, fx * (1 - fy)),
                           (ix0, iy1, (1 - fx) * fy),
                           (ix1, iy1, fx * fy)):
        out += image[iy, ix][:, channels].astype(np.float64) * weight
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


# WHAT THE MESH'S OWN TEXTURE COORDINATES CAN EXPRESS ------------------------
# The texture of a material may use another mapping channel than the mesh's
# own, or carry a transform (offset, repeat, rotation) of its own. The mesh's
# own coordinates do not express either, so then no colours are taken and the
# component says so (8.175).
def texture_problem(enabled=True, channel=1, transform_identity=True,
                    texture_coordinates=0, vertices=0):
    """Why the mesh's own texture coordinates cannot colour it from this
    texture: a text, or None when they can."""
    if not enabled:
        return 'the texture is switched off in the material'
    if not vertices or texture_coordinates != vertices:
        return 'the mesh has no texture coordinates'
    if channel != 1:
        return ('the texture uses mapping channel %s, not the mesh\'s own '
                'texture coordinates' % channel)
    if not transform_identity:
        return ('the material moves, scales or rotates the texture (a '
                'texture transform the mesh\'s texture coordinates do not '
                'express)')
    return None


def uv_transform_is_identity(matrix, tolerance=1e-9):
    """Whether a 4 x 4 texture transform leaves the u and v of the mesh as
    they are: the 2 x 2 block of u and v is the identity and u and v are not
    moved. The w row and column do not matter (a texture is flat; the
    transform Rhino stores for a render material has 0 there, so its own
    ``IsIdentity`` says False for a texture that is not transformed)."""
    m = np.asarray(matrix, dtype=np.float64).reshape(4, 4)
    wanted = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    block = m[0:2, [0, 1, 3]]            # u, v, and the move of u and v
    return bool(np.all(np.abs(block - wanted) <= tolerance))


def too_large(width, height):
    """True when an image has more pixels than are read."""
    return int(width) * int(height) > MAX_PIXELS
