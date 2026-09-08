#!/usr/bin/env python3.9
"""
Descriptor specifications.

One `DescriptorSpec` per descriptor family. Add or change descriptors here;
the cron runner (`main_descriptors_simple.py`) discovers them automatically
via `ALL_SPECS`.

Each spec owns:
    - `output_keys`: which ``descriptors.*`` fields it writes;
    - `params`: default parameters passed to the compute function;
    - `applicability_filter`: optional Mongo-style component-type gate;
    - `requires_mesh`: whether a reconstructed mesh is required.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from __future__ import annotations

from typing import Any, Dict, List

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.descriptors.registry import DescriptorContext, DescriptorSpec

from apps.descriptors.boxscore import compute_boxscore_with_metadata
from apps.descriptors.spherescore import compute_spherescore_with_metadata
from apps.descriptors.linescore import compute_linescore_with_metadata
from apps.descriptors.planescore import compute_planescore_with_metadata
from apps.descriptors import radial_signature as rs
from apps.descriptors.outline import (
    DEFAULT_CONCAVITY,
    outline_from_component,
    policy_for,
)


# SCALAR SCORE DESCRIPTORS ---------------------------------------------------

# All four "shape abstraction fitness" scores share the same shape:
# run a *_with_metadata function over the mesh with a `factor` param,
# emit a single float under their name. They apply to every component
# type (a sheet *can* have a spherescore, it will just be low).

def _boxscore(ctx: DescriptorContext) -> Dict[str, float]:
    data = compute_boxscore_with_metadata(ctx.mesh, **ctx.params)
    score = float(data['score'])
    ctx.log(f'boxscore = {score:.6f} (params: {dict(ctx.params)})')
    return {'boxscore': score}


BOXSCORE = DescriptorSpec(
    name='boxscore',
    output_keys=('boxscore',),
    compute=_boxscore,
    params={'factor': 100.0},
)


def _spherescore(ctx: DescriptorContext) -> Dict[str, float]:
    data = compute_spherescore_with_metadata(ctx.mesh, **ctx.params)
    score = float(data['score'])
    ctx.log(f'spherescore = {score:.6f} (params: {dict(ctx.params)})')
    return {'spherescore': score}


SPHERESCORE = DescriptorSpec(
    name='spherescore',
    output_keys=('spherescore',),
    compute=_spherescore,
    params={'factor': 100.0},
)


def _linescore(ctx: DescriptorContext) -> Dict[str, float]:
    data = compute_linescore_with_metadata(ctx.mesh, **ctx.params)
    score = float(data['score'])
    ctx.log(f'linescore = {score:.6f} (params: {dict(ctx.params)})')
    return {'linescore': score}


LINESCORE = DescriptorSpec(
    name='linescore',
    output_keys=('linescore',),
    compute=_linescore,
    params={'factor': 100.0},
)


def _planescore(ctx: DescriptorContext) -> Dict[str, float]:
    data = compute_planescore_with_metadata(ctx.mesh, **ctx.params)
    score = float(data['score'])
    ctx.log(f'planescore = {score:.6f} (params: {dict(ctx.params)})')
    return {'planescore': score}


PLANESCORE = DescriptorSpec(
    name='planescore',
    output_keys=('planescore',),
    compute=_planescore,
    params={'factor': 100.0},
)


# RADIAL SIGNATURE (planar components only) ----------------------------------

def _radial_signature(ctx: DescriptorContext) -> Dict[str, Any]:
    # The component type selects the policy rather than gating the spec:
    # every type can carry the signature, but a panel is reduced to its
    # silhouette in a canonical rotation while everything else is cut
    # through its PCA centre plane and left in the frame's orientation.
    policy = policy_for(ctx.component)
    outline, source, reason = outline_from_component(
        ctx.component,
        mesh=ctx.mesh,
        concavity=float(ctx.params.get('concavity', DEFAULT_CONCAVITY)),
        policy=policy,
        meshes_dir=ctx.meshes_dir,
        point_clouds_dir=ctx.point_clouds_dir,
        logger=lambda m: ctx.log(f'radial_signature: {m}'),
    )
    if outline is None:
        ctx.log(f'radial_signature: cannot compute ({reason})')
        return {}

    resolutions = tuple(
        ctx.params.get('resolutions', rs.SUPPORTED_RESOLUTIONS)
    )
    num_rest_angles = int(
        ctx.params.get('num_rest_angles', rs.DEFAULT_REST_ANGLES)
    )
    sigs = rs.compute_radial_signatures(
        profile=outline,
        resolutions=resolutions,
        num_rest_angles=num_rest_angles,
        rest_align=policy.rest_align,
    )
    any_sig = next(iter(sigs.values()))
    ctx.log(
        f'radial_signature: source={source}, '
        f'outline_points={len(outline)}, '
        f'resolutions={list(resolutions)}, '
        f'rest_align={policy.rest_align}, '
        f'rest_angle_deg={any_sig["rest_angle_deg"]:.3f}'
    )
    return rs.flatten_signatures_to_descriptors(sigs)


RADIAL_SIGNATURE = DescriptorSpec(
    name='radial_signature',
    output_keys=tuple(
        rs.descriptor_keys_for_resolutions(rs.SUPPORTED_RESOLUTIONS)
    ),
    compute=_radial_signature,
    params={
        'resolutions': list(rs.SUPPORTED_RESOLUTIONS),
        'num_rest_angles': rs.DEFAULT_REST_ANGLES,
        'concavity': DEFAULT_CONCAVITY,
    },
    # No filter: like the scores, this applies to every component type, and
    # the compute function reports why when the geometry cannot yield an
    # outline.
    applicability_filter=None,
    # False, not True: a mesh is only one of three outline sources, and an
    # extrusion-only or cloud-only component must still be computable when
    # the runner had no reason to load one.
    requires_mesh=False,
)


# REGISTRY -------------------------------------------------------------------

ALL_SPECS: List[DescriptorSpec] = [
    BOXSCORE,
    SPHERESCORE,
    LINESCORE,
    PLANESCORE,
    RADIAL_SIGNATURE,
]
"""
All descriptor specifications known to the runner.

Order is not significant for correctness (each spec is computed
independently), but the runner logs specs in registry order.
"""
