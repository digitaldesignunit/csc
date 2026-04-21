#!/usr/bin/env python3.9
"""
Descriptor registry.

Each descriptor (family) is declared as a single `DescriptorSpec` that owns
everything the cron runner needs to know about it:
    - which DB fields it writes (`output_keys`);
    - which component types it applies to (`applicability_filter`);
    - how to compute it (`compute` + `params`);
    - whether it needs a reconstructed mesh (`requires_mesh`).

The runner iterates over specs uniformly and never mentions individual
descriptor names. To add a new descriptor, add one `DescriptorSpec` in
`specs.py`; no changes elsewhere in the dispatcher are needed.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
)

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import trimesh


# PUBLIC TYPES ---------------------------------------------------------------

LoggerFn = Callable[[str], None]
"""Signature of a logger callback passed into descriptor compute functions."""


def _noop_logger(_message: str) -> None:
    """Default logger used when the caller does not supply one."""
    return None


@dataclass
class DescriptorContext:
    """All inputs a descriptor compute function is allowed to see.

    Keeping this explicit and small means specs cannot reach into private
    runner state, and it is cheap to construct in tests.
    """
    component: Dict[str, Any]
    mesh: Optional[trimesh.Trimesh] = None
    params: Mapping[str, Any] = field(default_factory=dict)
    log: LoggerFn = _noop_logger


ComputeFn = Callable[[DescriptorContext], Dict[str, Any]]
"""A spec's compute function: takes a context, returns a flat dict of DB
field values to write under ``descriptors.*``. Keys must be a subset of
the spec's declared `output_keys`.
"""


@dataclass(frozen=True)
class DescriptorSpec:
    """Static declaration of how to compute and store one descriptor family.

    Attributes:
        name: Logical family name for logging (e.g. ``"boxscore"``,
            ``"radial_signature"``). Does not have to equal any DB key.
        output_keys: DB field names (under ``descriptors.*``) this spec
            writes. A spec with multiple keys (e.g. the radial family) is
            considered "missing" if any one of them is absent or None.
        compute: Callable that produces the descriptor values from a
            `DescriptorContext`.
        params: Default parameters merged into the context when compute
            runs. Kept here, not in the runner, so params travel with the
            spec.
        applicability_filter: Optional Mongo-style filter (using only
            ``$in``, ``$exists``, ``$ne`` operators plus literal equality)
            restricting which components this spec applies to. ``None``
            means "applies to every component". The same filter is used
            both in the Mongo missing-descriptor query and in an in-memory
            recheck before compute.
        requires_mesh: If True, the runner must supply a non-None mesh.
            If False, the spec works purely from the component document
            (e.g. radial signature reads the extrusion profile).
    """
    name: str
    output_keys: Tuple[str, ...]
    compute: ComputeFn
    params: Mapping[str, Any] = field(default_factory=dict)
    applicability_filter: Optional[Mapping[str, Any]] = None
    requires_mesh: bool = True

    def is_applicable(self, component: Mapping[str, Any]) -> bool:
        """Return True if this spec applies to `component`.

        Evaluated in-memory using the same filter used for the Mongo
        query, so runtime and query semantics stay in lockstep.
        """
        f = self.applicability_filter
        if not f:
            return True
        return _matches_filter(component, f)


# FILTER EVALUATION ----------------------------------------------------------


def _get_dotted(doc: Mapping[str, Any], path: str) -> Any:
    """Resolve a dotted ``a.b.c`` path; return None if any hop is missing."""
    cur: Any = doc
    for part in path.split('.'):
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _matches_filter(doc: Mapping[str, Any], filt: Mapping[str, Any]) -> bool:
    """Minimal in-memory Mongo-filter evaluator.

    Supports only the operators the registry emits: ``$in``, ``$exists``,
    ``$ne``, plus literal-value equality. Raises on any other operator so
    we fail loudly if the query builder grows without the matcher catching
    up.
    """
    for key, expected in filt.items():
        value = _get_dotted(doc, key)
        if isinstance(expected, Mapping):
            for op, operand in expected.items():
                if op == '$in':
                    if value not in operand:
                        return False
                elif op == '$exists':
                    exists = value is not None
                    if exists != bool(operand):
                        return False
                elif op == '$ne':
                    if value == operand:
                        return False
                else:
                    raise ValueError(
                        f'Unsupported filter operator in registry matcher: '
                        f'{op!r}'
                    )
        else:
            if value != expected:
                return False
    return True


# MISSINGNESS + QUERY BUILDING -----------------------------------------------


def is_missing(component: Mapping[str, Any], spec: DescriptorSpec) -> bool:
    """True iff any of the spec's output keys is absent or None on the doc."""
    descriptors = component.get('descriptors') or {}
    for key in spec.output_keys:
        if key not in descriptors or descriptors.get(key) is None:
            return True
    return False


def build_missing_query(specs: Iterable[DescriptorSpec]) -> Dict[str, Any]:
    """Build a Mongo query matching components missing at least one spec.

    For each spec, a clause of the form
        (applicability_filter) AND (any output key missing)
    is OR-combined. A top-level catch-all for components with no
    ``descriptors`` field at all is also included.
    """
    or_conditions: List[Dict[str, Any]] = [
        {'descriptors': {'$exists': False}}
    ]
    for spec in specs:
        key_missing_clauses: List[Dict[str, Any]] = []
        for key in spec.output_keys:
            field_path = f'descriptors.{key}'
            key_missing_clauses.append({field_path: {'$exists': False}})
            key_missing_clauses.append({field_path: None})
        any_key_missing: Dict[str, Any] = {'$or': key_missing_clauses}
        if spec.applicability_filter:
            or_conditions.append({
                '$and': [dict(spec.applicability_filter), any_key_missing]
            })
        else:
            or_conditions.append(any_key_missing)
    return {'$or': or_conditions}


def missing_specs_for(
    component: Mapping[str, Any],
    specs: Iterable[DescriptorSpec]
) -> List[DescriptorSpec]:
    """Return the specs that both apply to `component` and are missing."""
    return [
        s for s in specs
        if s.is_applicable(component) and is_missing(component, s)
    ]


def collect_output_keys(specs: Iterable[DescriptorSpec]) -> List[str]:
    """Flatten all output keys across a set of specs (for logging)."""
    keys: List[str] = []
    for spec in specs:
        keys.extend(spec.output_keys)
    return keys


# EXECUTION ------------------------------------------------------------------


def compute_descriptor(
    spec: DescriptorSpec,
    component: Mapping[str, Any],
    mesh: Optional[trimesh.Trimesh],
    log: LoggerFn = _noop_logger,
) -> Dict[str, Any]:
    """Run a single spec and return its flattened output dict.

    On failure, returns ``{key: None, ...}`` for every output key of the
    spec so the caller can decide whether to persist the None sentinel or
    skip writing. A spec that cannot run at all (e.g. `requires_mesh=True`
    but mesh is None) returns an empty dict and logs a warning.
    """
    if spec.requires_mesh and mesh is None:
        log(f'{spec.name}: mesh not available, skipping')
        return {}
    context = DescriptorContext(
        component=dict(component),
        mesh=mesh,
        params=dict(spec.params),
        log=log,
    )
    try:
        out = spec.compute(context)
    except Exception as exc:
        log(f'{spec.name}: failed ({exc})')
        return {k: None for k in spec.output_keys}

    # Guard: only keep declared output keys so a buggy compute function
    # can never inject arbitrary fields into descriptors.*.
    return {k: v for k, v in out.items() if k in spec.output_keys}
