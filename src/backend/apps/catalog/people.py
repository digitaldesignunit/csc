#!/usr/bin/env python3.13
"""
Who a response names (decision 8.101). An anonymous caller never receives a
person: no username, name, ORCID, e-mail address or user id --- not the author
of a snapshot, the recorder, performer or reviewer of evidence, the user who
reserved a piece, nor the actor of a status change. The fields are dropped
(absent, not empty), by one function over the plain response body:
``strip_people``. Signed-in callers keep today's fields.

A key is a person's when it says so: ``user_id``, ``username``, ``email``,
``orcid``, ``full_name``, the ``reserved`` field (the id of the reserving user;
the status stays as ``is_reserved``), anything ending in ``_user_id`` or
``_username`` (``added_by_user_id``, ``recorded_by_username``, ...). An actor
(``performed_by``, ``assessed_by``, a verification's ``by``, a sampling's
``operator``) is a person or an organization: the organization stays, the name,
ORCID, role and e-mail go. Free text (notes, reasons) is not scanned.

Pure functions over plain documents; no database, no request.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Optional

PERSON_KEYS = frozenset({
    'user_id', 'username', 'email', 'orcid', 'full_name', 'reserved',
})
PERSON_SUFFIXES = ('_user_id', '_username')

# fields that hold an actor (or a list of them)
ACTOR_FIELDS = frozenset({'performed_by', 'assessed_by', 'by', 'operator'})
# what of an actor an anonymous caller does not get, besides the person keys
ACTOR_PERSON_KEYS = frozenset({'name', 'role'})


def is_person_key(key: Any) -> bool:
    return isinstance(key, str) and (
        key in PERSON_KEYS or key.endswith(PERSON_SUFFIXES))


def strip_actor(actor: Any) -> Any:
    """An actor without the person: the organization and its accreditation
    stay."""
    if not isinstance(actor, dict):
        return actor
    return {key: strip_people(item) for key, item in actor.items()
            if key not in ACTOR_PERSON_KEYS and not is_person_key(key)}


def strip_people(value: Any) -> Any:
    """A copy of a response body without the people named in it."""
    if isinstance(value, list):
        return [strip_people(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, item in value.items():
        if is_person_key(key):
            continue
        if key in ACTOR_FIELDS:
            out[key] = ([strip_actor(a) for a in item]
                        if isinstance(item, list) else strip_actor(item))
        else:
            out[key] = strip_people(item)
    return out


def for_viewer(body: Any, user: Optional[Any]) -> Any:
    """``body`` as the caller may see it: an anonymous caller (``user`` is
    None) gets no people, a signed-in one the body as it is (8.101)."""
    return strip_people(body) if user is None else body
