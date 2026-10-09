#!/usr/bin/env python3.13
"""
What a viewer sees of an evidence record (data model spec section 3.3.1,
7.3; decisions 6.13, 8.13, 8.17). Pure functions over plain documents.

Three tiers of viewer: anonymous (an ``is_public`` piece), signed in, and
member of the dataset (``admin`` counts). Actors: anonymous sees the
organization only; a signed-in user also the name, ORCID and role; the
e-mail address only ``admin`` and ``moderator(D)`` --- and never in a list.
For an anonymous caller every field that names a person is absent, not
empty (decision 8.101, ``people.strip_people``).
Attachments: anonymous readers get the list without file names, uploaders or
removal reasons; reasons and the status history's reasons never leave the
dataset (8.17: a reason may name the problem, e.g. a person in a photo).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
from typing import Any, Dict, List, Optional

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.people import strip_actor, strip_people

ANONYMOUS = 'anonymous'
SIGNED_IN = 'signed_in'
MEMBER = 'member'


def viewer_tier(*, logged_in: bool, member: bool) -> str:
    if not logged_in:
        return ANONYMOUS
    return MEMBER if member else SIGNED_IN


def project_actor(actor: Optional[Dict[str, Any]], tier: str, *,
                  email_ok: bool) -> Optional[Dict[str, Any]]:
    """One actor as the viewer may see it."""
    if actor is None:
        return None
    out = dict(actor)
    if not email_ok:
        out['email'] = None
    if tier == ANONYMOUS:
        out = strip_actor(out)
    return out


def project_attachment(entry: Dict[str, Any], tier: str, *, member: bool
                       ) -> Dict[str, Any]:
    """The public tier lists media type, size, checksum and date, so a
    holder of a copy can still check it (8.13)."""
    out = dict(entry)
    removed = out.get('removed')
    if removed and not member:
        out['removed'] = {'at': removed.get('at'), 'by_user_id': None,
                          'reason': None}
    if tier == ANONYMOUS:
        out['name'] = None
        if out.get('removed'):
            out['removed'] = {'at': out['removed'].get('at'),
                              'reason': None}
        out = strip_people(out)
    return out


def project_evidence(doc: Dict[str, Any], tier: str, *, email_ok: bool,
                     listing: bool = False) -> Dict[str, Any]:
    """The record as one viewer sees it. ``email_ok`` (admin or
    moderator(D)) never applies to a list response."""
    out = copy.deepcopy(doc)
    email = email_ok and not listing
    member = tier == MEMBER
    out['performed_by'] = [project_actor(a, tier, email_ok=email)
                           for a in out.get('performed_by') or []]
    verification = out.get('verification')
    if verification:
        verification['by'] = project_actor(verification.get('by'), tier,
                                           email_ok=email)
        if tier == ANONYMOUS:
            verification['note'] = None
    sampling = (out.get('payload') or {}).get('sampling')
    if isinstance(sampling, dict) and sampling.get('operator'):
        sampling['operator'] = project_actor(sampling['operator'], tier,
                                             email_ok=email)
    out['attachments'] = [
        project_attachment(a, tier, member=member)
        for a in out.get('attachments') or []]
    history = []
    for change in out.get('status_history') or []:
        change = dict(change)
        if not member:
            change['reason'] = None
        history.append(change)
    out['status_history'] = history
    return strip_people(out) if tier == ANONYMOUS else out


def evidence_tombstone(record: Dict[str, Any], identity: Dict[str, Any]
                       ) -> Dict[str, Any]:
    """What a withdrawn record (or a record of a withdrawn identity) shows
    outside its dataset (8.17): never the reason, the content or the
    files."""
    if record.get('status') == 'withdrawn':
        at = record.get('status_changed_at')
    else:
        at = (identity.get('withdrawn') or {}).get('at')
    return {'_id': record['_id'], 'kind': 'evidence', 'status': 'withdrawn',
            'withdrawn_at': at, 'catalog_number': identity.get(
                'catalog_number'),
            'identity_id': identity['_id'],
            'current_snapshot_id': identity.get('current_snapshot_id'),
            'duplicate_of': (identity.get('withdrawn') or {}).get(
                'duplicate_of'),
            'version': None}


def attachment_list(doc: Dict[str, Any], tier: str, *, member: bool
                    ) -> List[Dict[str, Any]]:
    return [project_attachment(a, tier, member=member)
            for a in doc.get('attachments') or []]
