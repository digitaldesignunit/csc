#!/usr/bin/env python3.13
"""
The profile of an account in the records it takes part in (decision 8.133 e):
when an evidence record or an origin is written, an actor of kind ``user``
gets the empty ``name`` / ``organization`` / ``organization_ror`` / ``url`` /
``orcid`` from that account's profile. A copy at write time: typed values win, and a
later change of the profile never rewrites a record.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Dict, Iterable, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import Request

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.profile import fill_actor

PROFILE_FIELDS = {'_id': 1, 'full_name': 1, 'organization': 1,
                  'organization_ror': 1, 'organization_url': 1, 'orcid': 1}


async def profiles_of(request: Request, user_ids: Iterable[str]
                      ) -> Dict[str, Dict[str, Any]]:
    """The profile fields of the accounts, by id (one query)."""
    ids = sorted({i for i in user_ids if i})
    if not ids:
        return {}
    rows = await request.app.mongodb_users.find(
        {'_id': {'$in': ids}}, PROFILE_FIELDS).to_list(length=None)
    return {row['_id']: row for row in rows}


async def fill_actors(request: Request, actors: Optional[List[Any]]
                      ) -> List[Any]:
    """The actors with their empty profile fields filled; the input is not
    changed."""
    actors = list(actors or [])
    wanted = [a.get('user_id') for a in actors
              if isinstance(a, dict) and a.get('kind') == 'user']
    profiles = await profiles_of(request, wanted)
    return [fill_actor(a, profiles.get(a.get('user_id') if isinstance(
        a, dict) else None, {})) for a in actors]


async def fill_origin(request: Request, origin: Optional[Dict[str, Any]]
                      ) -> Optional[Dict[str, Any]]:
    """The origin with the actors of its ``performed_by`` filled."""
    if not isinstance(origin, dict) or not origin.get('performed_by'):
        return origin
    return {**origin,
            'performed_by': await fill_actors(request,
                                              origin['performed_by'])}
