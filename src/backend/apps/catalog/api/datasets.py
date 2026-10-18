#!/usr/bin/env python3.13
"""
Datasets, memberships and the caller's roles (data model spec section 3.6,
section 7.7; plan P3).

* ``GET /users/me`` --- the caller with the global role and the roles per
  dataset; the frontend shows controls from this (nothing role-related is
  in the session token besides the global role).
* ``GET /datasets`` --- the datasets the caller can see, with the caller's
  roles in each; ``GET /datasets/{did}`` adds the members for
  ``moderator(D)`` and admin.
* ``POST /datasets`` (admin), ``PATCH /datasets/{did}`` and
  ``PUT /datasets/{did}/members/{user_id}`` (``moderator(D)``).
* ``POST /datasets/{did}/public`` --- every published, not withdrawn piece of
  the dataset public or private at once (``moderator(D)``, 8.131 c).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import re
import unicodedata
from typing import Annotated, Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pymongo.errors import DuplicateKeyError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Dataset
from settings import get_settings
from apps.catalog.models import User
from apps.catalog.profile import (
    clean_text,
    normalize_orcid,
    normalize_ror,
)
from apps.catalog.permissions import dataset_roles
from apps.catalog.vocab import (
    DATASET_ROLES,
    ActorRole,
    DatasetRole,
    Visibility,
)
from services import email_service
from .access import (
    EVER_PUBLISHED,
    and_match,
    load_dataset,
    load_datasets,
    refuse_unreviewed,
    require,
    viewer_of,
    visible_identity_match,
)
from .auth import get_current_active_user, get_optional_current_user
from .invitations import deliver
from .catalog_common import now_iso
from .identity_edit import _validated as _validated_identity
from .identity_edit import _write as _write_identity

from logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter()


# RESPONSES -------------------------------------------------------------------
class Membership(BaseModel):
    dataset: str
    name: str
    visibility: Visibility
    roles: List[DatasetRole]


class Me(BaseModel):
    id: str = Field(alias='_id')
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str
    # datasets the caller holds roles in (admin: implicit, not listed)
    memberships: List[Membership]
    # slugs where the caller moderates; admin: every dataset
    moderated_datasets: List[str]
    # the personal profile (8.133)
    organization: Optional[str] = None
    organization_ror: Optional[str] = None
    orcid: Optional[str] = None
    default_role: ActorRole = 'operator'

    model_config = {'populate_by_name': True}


class DatasetMemberView(BaseModel):
    user_id: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    roles: List[DatasetRole]
    added_at: Optional[str] = None


class DatasetView(BaseModel):
    id: str = Field(alias='_id')
    name: str
    description: Optional[str] = None
    visibility: Visibility
    # the caller's roles here (admin: every role)
    roles: List[DatasetRole]
    # an admin has reviewed it: until then it cannot be `catalog` and its
    # pieces cannot be public (8.139)
    reviewed: bool = True
    # moderator(D) and admin only
    members: Optional[List[DatasetMemberView]] = None
    member_count: Optional[int] = Field(
        default=None,
        description='list rows only: how many people are members; '
                    'moderator(D) and admin only, else absent')
    component_count: Optional[int] = Field(
        default=None,
        description='list rows only: published pieces the caller may see')

    model_config = {'populate_by_name': True}


class DatasetCreate(BaseModel):
    id: Optional[str] = Field(
        None, alias='_id',
        description='slug, immutable; admins only: an account\'s dataset '
                    'gets one derived from its name')
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    visibility: Visibility = 'members'

    model_config = {'populate_by_name': True}


class DatasetPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    visibility: Optional[Visibility] = None
    reviewed: Optional[bool] = Field(
        None, description='admin only: the dataset may be catalog and its '
                          'pieces public (8.139)')


class MemberRoles(BaseModel):
    roles: List[DatasetRole] = Field(
        description='the full set of roles; empty removes the member')


def _ordered(roles) -> List[str]:
    return [r for r in DATASET_ROLES if r in roles]


async def _member_views(request: Request, dataset: Dataset, *,
                        with_email: bool) -> List[DatasetMemberView]:
    """The members of a dataset. The e-mail addresses are shown to admins
    and to moderators of a reviewed dataset only (8.144 d): a moderator of a
    dataset nobody has reviewed sees username and name."""
    ids = [m.user_id for m in dataset.members]
    users = {u['_id']: u for u in await request.app.mongodb_users.find(
        {'_id': {'$in': ids}},
        {'username': 1, 'full_name': 1, 'email': 1}).to_list(length=None)}
    return [DatasetMemberView(
        user_id=m.user_id,
        username=users.get(m.user_id, {}).get('username'),
        full_name=users.get(m.user_id, {}).get('full_name'),
        email=users.get(m.user_id, {}).get('email') if with_email else None,
        roles=_ordered(m.roles),
        added_at=m.added_at) for m in dataset.members]


async def _component_counts(request: Request, viewer) -> Dict[str, int]:
    """Published pieces per dataset that the caller may see: the same
    visibility match as the catalog lists (3.6), withdrawn ones left out."""
    match = and_match(
        await visible_identity_match(request, viewer),
        {'current_snapshot_id': {'$ne': None}, 'withdrawn': None})
    cursor = await request.app.mongodb_component_identities.aggregate([
        {'$match': match},
        {'$group': {'_id': '$dataset', 'count': {'$sum': 1}}},
    ])
    return {row['_id']: int(row['count']) async for row in cursor}


async def _dataset_view(request: Request, user: Optional[User],
                        dataset: Dataset, *,
                        with_members: bool) -> DatasetView:
    roles = dataset_roles(viewer_of(user), dataset)
    members = None
    if with_members and 'moderator' in roles:
        viewer = viewer_of(user)
        members = await _member_views(
            request, dataset,
            with_email=viewer.is_admin or dataset.reviewed)
    return DatasetView(_id=dataset.id, name=dataset.name,
                       description=dataset.description,
                       visibility=dataset.visibility,
                       reviewed=dataset.reviewed,
                       roles=_ordered(roles), members=members)


# ROUTES ----------------------------------------------------------------------
@router.get('/users/me', response_model=Me, response_model_by_alias=True,
            summary='The caller, with the roles per dataset')
async def get_me(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    viewer = viewer_of(current_user)
    datasets = (await load_datasets(request)).values()
    memberships = [
        Membership(dataset=d.id, name=d.name, visibility=d.visibility,
                   roles=_ordered(d.roles_of(current_user.id)))
        for d in sorted(datasets, key=lambda d: d.id)
        if d.roles_of(current_user.id)]
    moderated = sorted(d.id for d in datasets
                       if 'moderator' in dataset_roles(viewer, d))
    return _me_view(current_user, memberships, moderated)


def _me_view(user: User, memberships: List[Membership],
             moderated: List[str]) -> Me:
    return Me(_id=user.id, username=user.username, full_name=user.full_name,
              email=user.email, role=user.role, memberships=memberships,
              moderated_datasets=moderated,
              organization=user.organization,
              organization_ror=user.organization_ror, orcid=user.orcid,
              default_role=user.default_role or 'operator')


class ProfilePatch(BaseModel):
    """What an account edits of itself (8.133): only the fields sent change;
    an empty text clears an optional one."""
    model_config = ConfigDict(extra='forbid')

    full_name: Optional[str] = Field(None, max_length=200)
    organization: Optional[str] = Field(None, max_length=200)
    organization_ror: Optional[str] = Field(None, max_length=200)
    orcid: Optional[str] = Field(None, max_length=60)
    default_role: Optional[ActorRole] = None


@router.patch('/users/me', response_model=Me, response_model_by_alias=True,
              summary='Edit the caller\'s profile (8.133)')
async def patch_me(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: ProfilePatch,
):
    """``full_name``, ``organization``, ``organization_ror`` (a ROR id or
    URL), ``orcid`` (format and check digit) and ``default_role``. Records
    take the values over when they are written; a later change never rewrites
    a record."""
    sent = body.model_dump(exclude_unset=True)
    changes: Dict[str, Any] = {}
    try:
        if 'full_name' in sent:
            name = clean_text(sent['full_name'])
            if name is None:
                raise ValueError('the name cannot be empty')
            changes['full_name'] = name
        if 'organization' in sent:
            changes['organization'] = clean_text(sent['organization'])
        if 'organization_ror' in sent:
            changes['organization_ror'] = (
                normalize_ror(sent['organization_ror'])
                if clean_text(sent['organization_ror']) else None)
        if 'orcid' in sent:
            changes['orcid'] = (normalize_orcid(sent['orcid'])
                                if clean_text(sent['orcid']) else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if sent.get('default_role') is not None:
        changes['default_role'] = sent['default_role']
    elif 'default_role' in sent:
        changes['default_role'] = None
    if changes:
        await request.app.mongodb_users.update_one(
            {'_id': current_user.id}, {'$set': changes})
    return await get_me(request, current_user.model_copy(update=changes))


@router.get('/datasets', response_model=List[DatasetView],
            response_model_by_alias=True, response_model_exclude_none=True,
            summary='Datasets the caller can see, with the caller\'s roles')
async def list_datasets(
    request: Request,
    current_user: Annotated[Optional[User],
                            Depends(get_optional_current_user)],
):
    """Admin: all. Signed in: member of, or ``catalog``. Anonymous: those
    holding public components (3.6)."""
    viewer = viewer_of(current_user)
    datasets = sorted((await load_datasets(request)).values(),
                      key=lambda d: d.id)
    counts = await _component_counts(request, viewer)
    if viewer.is_admin:
        shown = datasets
    elif viewer.logged_in:
        shown = [d for d in datasets if dataset_roles(viewer, d)
                 or d.visibility == 'catalog']
    else:
        # an anonymous caller sees a dataset by what the pieces below show:
        # published, not withdrawn, public (S13, 8.144) --- the match the
        # counts use, so a list entry never shows a count of zero
        shown = [d for d in datasets if counts.get(d.id)]
    views = []
    for d in shown:
        view = await _dataset_view(request, current_user, d, with_members=False)
        view.component_count = counts.get(d.id, 0)
        if 'moderator' in dataset_roles(viewer, d):
            view.member_count = len(d.members)
        views.append(view)
    return views


@router.get('/datasets/{did}', response_model=DatasetView,
            response_model_by_alias=True, response_model_exclude_none=True,
            summary='One dataset; members for moderator(D) and admin')
async def get_dataset(
    request: Request,
    current_user: Annotated[Optional[User],
                            Depends(get_optional_current_user)],
    did: str,
):
    dataset = (await load_dataset(request, current_user, did)).record
    return await _dataset_view(request, current_user, dataset,
                               with_members=True)


MAX_DATASETS_ENV = 'CSC_MAX_DATASETS_PER_USER'


def max_datasets_per_user() -> int:
    """How many datasets one account may create (8.139 e); admins have no
    limit. ``CSC_MAX_DATASETS_PER_USER``, 3 when unset or not a number."""
    return get_settings().csc_max_datasets_per_user


def slug_from_name(name: str) -> str:
    """A slug from a dataset name (8.139 d): ASCII lower-case letters,
    digits and underscores, 2 to 55 characters (room for a collision suffix)."""
    folded = unicodedata.normalize('NFKD', name).encode(
        'ascii', 'ignore').decode('ascii').lower()
    slug = re.sub(r'[^a-z0-9]+', '_', folded).strip('_')[:55].strip('_')
    if not slug:
        slug = 'dataset'
    return slug if len(slug) >= 2 else f'{slug}_x'


async def _free_slug(request: Request, name: str, taken=()) -> str:
    """The slug of ``name``, or with ``_2``, ``_3`` ... when it is taken."""
    base = slug_from_name(name)
    existing = set(await request.app.mongodb_datasets.distinct('_id')) | set(
        taken)
    slug, n = base, 1
    while slug in existing:
        n += 1
        slug = f'{base}_{n}'
    return slug


async def _notify_admins(request: Request, dataset: Dataset,
                         creator: User) -> None:
    """The "Dataset created" mail to the admins (8.139 i, 8.124 template).
    Whatever happens here never blocks the create."""
    try:
        admins = await request.app.mongodb_users.find(
            {'role': 'admin', 'disabled': {'$ne': True},
             'email': {'$nin': [None, '']}}, {'email': 1}).to_list(
            length=None)
        if not admins:
            return
        config = email_service.load_email_config()
        by = creator.full_name or creator.username
        failures = await deliver(request, [
            email_service.dataset_created_mail(
                config, admin['email'], dataset.name, dataset.id, by,
                creator.email) for admin in admins])
        for failure in failures:
            if failure is not None:
                log.warning('"dataset created" mail failed: %s',
                            email_service.failure_kind(failure))
    except Exception as exc:                               # noqa: BLE001
        log.warning('"dataset created" mail failed: %s', type(exc).__name__)


@router.post('/datasets', response_model=DatasetView, status_code=201,
             response_model_by_alias=True, response_model_exclude_none=True,
             summary='Create a dataset (a verified account, or an admin)')
async def create_dataset(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: DatasetCreate,
):
    """An account with a verified e-mail address creates a dataset of its own
    (8.139): the slug is derived from the name, the creator becomes
    ``moderator`` and ``contributor``, the dataset is ``members`` and not
    reviewed, and each account may create ``CSC_MAX_DATASETS_PER_USER`` of
    them (3). An admin may state the slug, creates reviewed datasets and has
    no limit. The admins get a "Dataset created" mail for an account's
    dataset."""
    any_dataset = Dataset.model_validate({
        '_id': 'new', 'name': 'new', 'created': now_iso(),
        'lastmodified': now_iso()})
    await require(request, current_user, 'create_dataset',
                  dataset=any_dataset)
    admin = viewer_of(current_user).is_admin
    datasets = request.app.mongodb_datasets
    if not admin:
        if not current_user.email_verified:
            raise HTTPException(
                status_code=403,
                detail='Verify your e-mail address before you create a '
                       'dataset.')
        if body.id is not None:
            raise HTTPException(
                status_code=422,
                detail='The slug of a dataset is derived from its name.')
        if body.visibility != 'members':
            raise HTTPException(
                status_code=409,
                detail='A new dataset is visible to its members only until '
                       'an admin has reviewed it.')
        limit = max_datasets_per_user()
        if await datasets.count_documents(
                {'created_by_user_id': current_user.id}) >= limit:
            raise HTTPException(
                status_code=403,
                detail=f'You have created {limit} datasets, the most one '
                       f'account may create. Ask an admin for another.')
    now = now_iso()
    members = [] if admin else [{
        'user_id': current_user.id, 'roles': _ordered({'moderator',
                                                       'contributor'}),
        'added_by_user_id': current_user.id, 'added_at': now}]
    explicit = body.id if admin and body.id else None
    for _ in range(5):
        slug = explicit or await _free_slug(request, body.name)
        try:
            dataset = Dataset.model_validate({
                '_id': slug, 'name': body.name.strip(),
                'description': body.description,
                'visibility': body.visibility, 'members': members,
                'reviewed': admin, 'created_by_user_id': current_user.id,
                'created': now, 'lastmodified': now})
        except ValidationError as exc:
            raise HTTPException(status_code=422,
                                detail=exc.errors()[0]['msg']) from exc
        try:
            await datasets.insert_one(
                dataset.model_dump(by_alias=True, mode='json'))
            break
        except DuplicateKeyError as exc:
            if explicit:
                raise HTTPException(status_code=409,
                                    detail=f'Dataset {body.id} exists') from exc
    else:
        raise HTTPException(status_code=409,
                            detail='No free slug for this name; try another.')
    request.state.csc_datasets = None
    if not admin:
        await _notify_admins(request, dataset, current_user)
    return await _dataset_view(request, current_user, dataset,
                               with_members=True)


@router.patch('/datasets/{did}', response_model=DatasetView,
              response_model_by_alias=True, response_model_exclude_none=True,
              summary='Name, description, visibility (moderator(D))')
async def patch_dataset(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    did: str,
    body: DatasetPatch,
):
    dataset = (await load_dataset(request, current_user, did,
                                  'edit_dataset')).record
    viewer = viewer_of(current_user)
    changes: Dict[str, Any] = body.model_dump(exclude_unset=True)
    if 'name' in changes and changes['name'] is None:
        raise HTTPException(status_code=422, detail='name cannot be empty')
    if 'reviewed' in changes:
        if changes['reviewed'] is None:
            raise HTTPException(status_code=422,
                                detail='reviewed is true or false')
        if not viewer.is_admin:
            raise HTTPException(status_code=403,
                                detail='Only an admin marks a dataset '
                                       'reviewed.')
    if changes.get('visibility') == 'catalog' \
            and dataset.visibility != 'catalog' \
            and not changes.get('reviewed', dataset.reviewed):
        refuse_unreviewed(dataset, viewer)
    if changes:
        changes['lastmodified'] = now_iso()
        await request.app.mongodb_datasets.update_one({'_id': did},
                                                      {'$set': changes})
        request.state.csc_datasets = None
    # the stored state, whatever the caller may still read of it: a moderator
    # who removed their own roles gets the answer, not a 403 after the write
    return await _dataset_view(request, current_user,
                               (await load_datasets(request))[did],
                               with_members=True)


@router.put('/datasets/{did}/members/{user_id}', response_model=DatasetView,
            response_model_by_alias=True, response_model_exclude_none=True,
            summary='Set a member\'s roles; empty removes (moderator(D))')
async def put_dataset_member(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    did: str,
    user_id: str,
    body: MemberRoles,
):
    dataset = (await load_dataset(request, current_user, did,
                                  'manage_members')).record
    if await request.app.mongodb_users.find_one({'_id': user_id},
                                                {'_id': 1}) is None:
        raise HTTPException(status_code=404, detail='User not found')
    roles = _ordered(set(body.roles))
    moderators_before = {m.user_id for m in dataset.members
                         if 'moderator' in m.roles}
    moderators_after = moderators_before - {user_id}
    if 'moderator' in roles:
        moderators_after |= {user_id}
    if moderators_before and not moderators_after \
            and not viewer_of(current_user).is_admin:
        # 8.139 g: a dataset keeps a moderator; an admin may take the last
        raise HTTPException(
            status_code=409,
            detail='A dataset keeps at least one moderator: add another '
                   'before you remove or demote the last one (an admin can '
                   'do it).')
    members = [m.model_dump(mode='json') for m in dataset.members
               if m.user_id != user_id]
    existing = next((m for m in dataset.members if m.user_id == user_id),
                    None)
    if roles:
        members.append({
            'user_id': user_id, 'roles': roles,
            'added_by_user_id': (existing.added_by_user_id if existing
                                 else current_user.id),
            'added_at': existing.added_at if existing else now_iso()})
    await request.app.mongodb_datasets.update_one(
        {'_id': did}, {'$set': {'members': members,
                                'lastmodified': now_iso()}})
    request.state.csc_datasets = None
    # the stored state, whatever the caller may still read of it: a moderator
    # who removed their own roles gets the answer, not a 403 after the write
    return await _dataset_view(request, current_user,
                               (await load_datasets(request))[did],
                               with_members=True)


class PublicBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    is_public: bool = Field(description='the flag to set on the pieces')
    dry_run: bool = Field(False, description='only count what would change')


class PublicResult(BaseModel):
    dataset: str
    is_public: bool
    # how many pieces changed (dry run: would change)
    changed: int
    dry_run: bool
    # pieces another edit changed in the meantime (left as they were)
    skipped: int = 0


@router.post('/datasets/{did}/public', response_model=PublicResult,
             summary='Make every published piece of a dataset public or '
                     'private (moderator(D))')
async def set_dataset_public(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    did: str,
    body: PublicBody,
):
    """Sets ``is_public`` on the pieces of the dataset that were ever
    published (3.1.5) and are not withdrawn, where the flag differs, and logs
    each change like a metadata PATCH (``cause: patch``). Unpublished and
    withdrawn pieces are left alone, and so are children: no piece follows
    another (6.2). ``dry_run`` only counts."""
    dataset = (await load_dataset(request, current_user, did,
                                  'set_dataset_public')).record
    if body.is_public and not body.dry_run:
        refuse_unreviewed(dataset, viewer_of(current_user))      # 8.139 c
    identities = request.app.mongodb_component_identities
    differs = ({'$ne': True} if body.is_public else True)
    candidates = await identities.find(
        {'dataset': did, 'withdrawn': None, 'is_public': differs}
    ).to_list(length=None)
    ever = set(await request.app.mongodb_component_snapshots.distinct(
        'identity_id', {'identity_id': {'$in': [c['_id'] for c in candidates]},
                        'status': {'$in': list(EVER_PUBLISHED)}}))
    pieces = [c for c in candidates
              if c.get('current_snapshot_id') or c['_id'] in ever]
    if body.dry_run:
        return PublicResult(dataset=did, is_public=body.is_public,
                            changed=len(pieces), dry_run=True)
    # validate every piece first: one that does not pass stops the whole
    # change before anything is written (and is named), instead of a 422
    # after earlier pieces were already written
    afters: List[tuple] = []
    invalid: Dict[str, str] = {}
    for identity in pieces:
        try:
            afters.append((identity, _validated_identity(
                {**identity, 'is_public': body.is_public})))
        except HTTPException as exc:
            invalid[identity['_id']] = str(exc.detail)
    if invalid:
        raise HTTPException(status_code=422, detail={
            'message': f'{len(invalid)} of {len(pieces)} pieces do not pass '
                       f'validation; nothing was changed. Correct them first.',
            'pieces': invalid})
    changed = skipped = 0
    for identity, after in afters:
        try:
            written = await _write_identity(
                request, identity, after, user_id=current_user.id,
                cause='patch')
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            skipped += 1
            continue
        if written is not None:
            changed += 1
    return PublicResult(dataset=did, is_public=body.is_public,
                        changed=changed, dry_run=body.dry_run,
                        skipped=skipped)


@router.delete('/datasets/{did}', status_code=200,
               summary='Delete an empty dataset (moderator(D), admin)')
async def delete_dataset(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    did: str,
):
    """Only while the dataset holds no piece at all (no identity, whatever
    its state; for an admin too: move the pieces first, ``move_identity``).
    The open invitations into it are revoked with it (8.139 f)."""
    await load_dataset(request, current_user, did, 'delete_dataset')
    pieces = await request.app.mongodb_component_identities.count_documents(
        {'dataset': did}, limit=1)
    if pieces:
        raise HTTPException(
            status_code=409,
            detail='The dataset still holds pieces: move them to another '
                   'dataset first.')
    now = now_iso()
    revoked = await request.app.mongodb_invitations.update_many(
        {'dataset': did, 'revoked_at': None, 'used_at': None},
        {'$set': {'revoked_at': now, 'revoked_by_user_id': current_user.id}})
    await request.app.mongodb_datasets.delete_one({'_id': did})
    request.state.csc_datasets = None
    return {'deleted': did, 'revoked_invitations': revoked.modified_count}


# CODEGEN ---------------------------------------------------------------------
class AccessTypesEnvelope(BaseModel):
    """Codegen only: the types of the access, dataset, invitation and user
    routes (``/schema/access`` --> frontend ``AccessModels.ts``)."""
    me: Me
    dataset: DatasetView
    tombstone: 'Tombstone'
    invitation: 'InvitationView'
    invite_result: 'InviteResult'
    member_result: 'MemberByEmailResult'
    invitation_preview: 'InvitationPreview'
    invitation_accepted: 'InvitationAccepted'
    admin_user: 'AdminUserRow'
    user_hit: 'UserHit'


@router.get('/schema/access', include_in_schema=False)
async def get_access_json_schema():
    from apps.catalog.read_models import Tombstone
    from .invitations import (InvitationAccepted, InvitationPreview,
                              InvitationView, InviteResult,
                              MemberByEmailResult)
    from .users import AdminUserRow, UserHit
    AccessTypesEnvelope.model_rebuild(_types_namespace={
        'Tombstone': Tombstone, 'InvitationView': InvitationView,
        'InviteResult': InviteResult,
        'MemberByEmailResult': MemberByEmailResult,
        'InvitationPreview': InvitationPreview,
        'InvitationAccepted': InvitationAccepted,
        'AdminUserRow': AdminUserRow, 'UserHit': UserHit})
    return AccessTypesEnvelope.model_json_schema(by_alias=True)
