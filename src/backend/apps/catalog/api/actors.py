#!/usr/bin/env python3.13
"""
GDPR redaction of a person (data model spec section 3.1.4, 3.8; decision
8.13; plan P6): ``POST /actors/redact`` --- admin.

In every evidence actor (``performed_by``, ``verification.by``, the core's
drilling operator) and every origin actor of an identity (current and
archived cycles) the person's ``name``, ``email`` and ``orcid`` become null
and ``redacted_at`` is set; the organization stays. The change log is
blanked the same way inside its old / new values. Files are not reached:
the response lists the attachments of records that name the person
(``performed_by``, ``recorded_by``, ``uploaded_by``) as the moderator's
worklist --- add a redacted copy, remove the original with the reason
``gdpr``.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
from typing import Annotated, Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.etag import compute_snapshot_etag
from apps.catalog.models import User
from .access import require
from .auth import get_current_active_user
from .catalog_common import now_iso

router = APIRouter()

RETRIES = 4
ACTOR_KINDS = ('user', 'person', 'organization')
PERSONAL = ('name', 'email', 'orcid')


class RedactBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    user_id: Optional[str] = Field(
        None, description='An account: every actor with this user_id')
    name: Optional[str] = Field(
        None, description='A person without an account: actors with this '
                          'name (and organization, if given). Without an '
                          'organization every actor of that name is blanked '
                          'in the whole catalogue, whoever they are: give '
                          'the organization where names are common. Run '
                          'with dry_run first.')
    organization: Optional[str] = Field(
        None, description='With name: only actors of this organization')
    dry_run: bool = Field(
        False, description='Count and list, change nothing')


def _matches(actor: Any, body: RedactBody) -> bool:
    """Whether a dict is an actor that names the person."""
    if not isinstance(actor, dict) or actor.get('kind') not in ACTOR_KINDS \
            or actor.get('redacted_at'):
        return False
    if body.user_id is not None:
        return actor.get('user_id') == body.user_id
    if (actor.get('name') or '').strip().lower() != \
            (body.name or '').strip().lower():
        return False
    if body.organization is not None:
        return (actor.get('organization') or '').strip().lower() == \
            body.organization.strip().lower()
    return True


def blank(value: Any, body: RedactBody, now: str) -> int:
    """Blank every matching actor inside ``value`` in place (any nesting);
    returns how many were blanked."""
    count = 0
    if isinstance(value, dict):
        if _matches(value, body):
            for key in PERSONAL:
                value[key] = None
            value['redacted_at'] = now
            return 1
        for child in value.values():
            count += blank(child, body, now)
    elif isinstance(value, list):
        for child in value:
            count += blank(child, body, now)
    return count


def _count(doc: Dict[str, Any], body: RedactBody, keys) -> int:
    """How many actors a redaction would blank in ``doc`` (dry run)."""
    probe = copy.deepcopy({k: doc.get(k) for k in keys})
    return blank(probe, body, '')


def _names(value: Any, body: RedactBody) -> bool:
    """Whether ``value`` holds an actor that names the person."""
    if isinstance(value, dict):
        return _matches(value, body) or any(
            _names(v, body) for v in value.values())
    if isinstance(value, list):
        return any(_names(v, body) for v in value)
    return False


@router.post('/actors/redact', summary='Redact a person (admin, GDPR Art 17)')
async def redact_actor(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: RedactBody,
):
    """Admin. The person is named by ``user_id`` or by ``name`` (+
    ``organization``). **A name without an organization blanks every actor
    of that name catalogue-wide**: use ``dry_run`` to see what it would
    touch. Writes are guarded by the record's etag (identity:
    ``lastmodified``) and retried; a record that keeps changing is a 409
    and the run can be repeated. Returns what was changed and the worklist
    of attachments to replace by redacted copies."""
    await require(request, current_user, 'redact_actor')
    if body.user_id is None and not (body.name or '').strip():
        raise HTTPException(status_code=422,
                            detail='user_id, or name (with organization)')
    now = now_iso()
    evidence = request.app.mongodb_component_evidence
    identities = request.app.mongodb_component_identities
    log = request.app.mongodb_change_log
    counts = {'evidence': 0, 'identities': 0, 'change_log': 0, 'actors': 0}
    worklist: List[Dict[str, Any]] = []

    async for doc in evidence.find({}):
        actors_hit = _names(doc.get('performed_by'), body) \
            or _names(doc.get('verification'), body) \
            or _names((doc.get('payload') or {}).get('sampling'), body)
        recorder = body.user_id is not None and \
            doc.get('recorded_by_user_id') == body.user_id
        uploaders = [a for a in doc.get('attachments') or []
                     if body.user_id is not None
                     and a.get('uploaded_by_user_id') == body.user_id]
        if actors_hit or recorder or uploaders:
            for entry in doc.get('attachments') or []:
                if not entry.get('removed'):
                    worklist.append({
                        'evidence_id': doc['_id'],
                        'identity_id': doc['identity_id'],
                        'index': entry['index'], 'name': entry.get('name'),
                        'media_type': entry.get('media_type'),
                        'sha256': entry.get('sha256'),
                        'status': doc.get('status'),
                        'why': [w for w, hit in (
                            ('performed_by', actors_hit),
                            ('recorded_by', recorder),
                            ('uploaded_by', bool(uploaders))) if hit]})
        if not actors_hit:
            continue
        counts['evidence'] += 1
        if body.dry_run:
            counts['actors'] += _count(doc, body, ('performed_by',
                                                   'verification', 'payload'))
            continue
        for _ in range(RETRIES):               # guarded by the etag
            updated = copy.deepcopy(doc)
            n = blank(updated.get('performed_by'), body, now) \
                + blank(updated.get('verification'), body, now) \
                + blank((updated.get('payload') or {}).get('sampling'),
                        body, now)
            updated['lastmodified'] = now
            updated['etag'] = compute_snapshot_etag(updated)
            if (await evidence.replace_one(
                    {'_id': doc['_id'], 'etag': doc.get('etag')},
                    updated)).matched_count:
                counts['actors'] += n
                break
            doc = await evidence.find_one({'_id': doc['_id']})
            if doc is None or not _names(doc.get('performed_by'), body) \
                    and not _names(doc.get('verification'), body) \
                    and not _names((doc.get('payload') or {}).get(
                        'sampling'), body):
                break                       # gone, or someone else did it
        else:
            raise HTTPException(status_code=409, detail=(
                f'Evidence {doc["_id"]} kept changing; run the redaction '
                f'again.'))

    async for doc in identities.find({}):
        if not (_names(doc.get('origin'), body)
                or _names(doc.get('past_cycles'), body)):
            continue
        counts['identities'] += 1
        if body.dry_run:
            counts['actors'] += _count(doc, body, ('origin', 'past_cycles'))
            continue
        for _ in range(RETRIES):               # guarded by lastmodified
            updated = copy.deepcopy(doc)
            n = blank(updated.get('origin'), body, now) \
                + blank(updated.get('past_cycles'), body, now)
            updated['lastmodified'] = now
            if (await identities.replace_one(
                    {'_id': doc['_id'],
                     'lastmodified': doc.get('lastmodified')},
                    updated)).matched_count:
                counts['actors'] += n
                break
            doc = await identities.find_one({'_id': doc['_id']})
            if doc is None or not (_names(doc.get('origin'), body)
                                   or _names(doc.get('past_cycles'), body)):
                break
        else:
            raise HTTPException(status_code=409, detail=(
                f'Identity {doc["_id"]} kept changing; run the redaction '
                f'again.'))

    async for entry in log.find({}):
        if not _names(entry.get('changes'), body):
            continue
        counts['change_log'] += 1
        if not body.dry_run:
            before = entry['changes']
            changes = copy.deepcopy(before)
            blank(changes, body, now)
            # an entry is immutable but for redaction: the write is guarded
            # by the content that was read
            await log.update_one({'_id': entry['_id'], 'changes': before},
                                 {'$set': {'changes': changes}})
    return JSONResponse(status_code=200, content={
        'dry_run': body.dry_run, **counts, 'worklist': worklist})
