#!/usr/bin/env python3.13
"""
Types of the evidence method registry (data model spec section 4.5).

One ``EvidenceMethodSpec`` per method; ``ALL_EVIDENCE_SPECS`` (specs.py)
drives the validation, ``GET /evidence/methods``, the JSON Schemas and the
web form. Adding a method means adding one spec.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import BaseModel


@dataclass(frozen=True)
class Problem:
    """One thing wrong with a record: where, and what."""
    path: str
    message: str

    def as_dict(self) -> Dict[str, str]:
        return {'path': self.path, 'message': self.message}


class EvidenceInvalid(Exception):
    """A record the registry refuses (an error of the spec, 422)."""

    def __init__(self, problems: List[Problem]):
        super().__init__('; '.join(f'{p.path}: {p.message}'
                                   for p in problems))
        self.problems = problems


@dataclass
class Prepared:
    """What a method makes of its payload: the payload with the server's
    fields filled in, the results it can derive itself, envelope values the
    payload decides, and what is wrong with it."""
    payload: Dict[str, Any]
    # the headline result the server derives; None = the client supplies it
    summary: Optional[Dict[str, Any]] = None
    # results the server builds (kinds listed in `server_derived_kinds`)
    derived: List[Dict[str, Any]] = field(default_factory=list)
    sampled_at: Optional[str] = None
    observed_at: Optional[str] = None
    # a position the payload dictates (a rebound grid is a region)
    position: Optional[Dict[str, Any]] = None
    errors: List[Problem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # the record is a real observation the fold must not use (a discarded
    # rebound set, a core with a longitudinal bar)
    excluded_from_fold: bool = False
    source_tier: Optional[str] = None


@dataclass(frozen=True)
class DerivedModelKind:
    """A model a ``derived[]`` result may name (decision 8.41): the quantity
    it yields, and the conditions the server checks. The server holds no
    table values of the models (DIN copyright): a class read from a table
    is the user's entry."""
    kind: str
    quantity: str
    label: str
    description: str
    # server-built: the client's entries of this kind are replaced
    server_built: bool = False
    # model.note / model.reference must be given
    needs_note: bool = False
    needs_reference: bool = False


@dataclass(frozen=True)
class EvidenceMethodSpec:
    name: str
    label: str
    description: str
    payload_model: Type[BaseModel]
    # None: decided by the payload (`tier_of`)
    source_tier: Optional[str]
    destructive: bool
    default_standard: Optional[Dict[str, Any]]
    # quantities the headline result may have; the first is the default
    summary_quantities: Tuple[str, ...]
    # 'measured' | 'claimed'; None: decided by the payload
    summary_kind: Optional[str]
    context_time: str                     # 'sampled_at' | 'observed_at'
    prepare: Callable[[BaseModel, Dict[str, Any]], Prepared]
    derived_kinds: Tuple[DerivedModelKind, ...] = ()
    tier_of: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None
    # the summary is client-supplied (a claim); False: derived by `prepare`
    summary_from_client: bool = False
    # a record may carry no summary: a document (decision 8.106)
    summary_optional: bool = False
    version: int = 1

    @property
    def server_derived_kinds(self) -> Tuple[str, ...]:
        return tuple(k.kind for k in self.derived_kinds if k.server_built)


@dataclass(frozen=True)
class PairingFacts:
    """What a core's pairing to a rebound record is checked against (8.42);
    loaded by the route."""
    identity_id: str
    rebound: Optional[Dict[str, Any]]          # the stored rebound record
    other_pairs: List[str]                      # ids of other cores that
    #                                             name the same rebound record
