#!/usr/bin/env python3.13
"""
Who may see and do what (data model spec section 3.6 and section 7.0).

Pure predicates, no database: the routes load the target's dataset (and the
parents' datasets where a rule needs them), build a ``Target`` and ask
``can(viewer, action, target)``. Enforcement lives only in the backend; the
frontend merely hides controls. ``admin`` passes every check.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, Optional, Tuple

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Dataset
from apps.catalog.vocab import DATASET_ROLES, DELETABLE_STATUSES

Roles = FrozenSet[str]


@dataclass(frozen=True)
class Viewer:
    """The caller: anonymous (``user_id`` None) or a user with a role."""
    user_id: Optional[str] = None
    role: Optional[str] = None      # 'user' | 'admin'; None when anonymous

    @property
    def logged_in(self) -> bool:
        return self.user_id is not None

    @property
    def is_admin(self) -> bool:
        return self.logged_in and self.role == 'admin'


ANONYMOUS = Viewer()


def dataset_roles(viewer: Viewer, dataset: Dataset) -> Roles:
    """The viewer's roles in a dataset; admin holds every role implicitly."""
    if viewer.is_admin:
        return frozenset(DATASET_ROLES)
    if not viewer.logged_in:
        return frozenset()
    return dataset.roles_of(viewer.user_id)


# VISIBILITY (section 3.6, 3.1.5, 7.0) ----------------------------------------
def can_see_component(
    viewer: Viewer,
    dataset: Dataset,
    *,
    is_public: bool,
    published: bool,
    created_by_user_id: Optional[str] = None,
) -> bool:
    """
    A published component: ``admin or member(D) or (logged in and D is
    catalog) or is_public``. An unpublished one (8.9): its creator and
    ``moderator(D)`` only.
    """
    roles = dataset_roles(viewer, dataset)
    if not published:
        return 'moderator' in roles or (
            viewer.logged_in and viewer.user_id == created_by_user_id)
    if viewer.is_admin or roles:
        return True
    if viewer.logged_in and dataset.visibility == 'catalog':
        return True
    return is_public


def can_see_record(
    viewer: Viewer,
    dataset: Dataset,
    *,
    kind: str,
    status: str,
    author_id: Optional[str],
    component_visible: bool,
) -> bool:
    """
    A snapshot or evidence record. Published / withdrawn ones follow the
    component's visibility; draft / pending / rejected ones are seen by the
    author, ``moderator(D)``, and ``reviewer(D)`` for pending evidence.
    """
    if status in ('published', 'withdrawn'):
        return component_visible
    roles = dataset_roles(viewer, dataset)
    if 'moderator' in roles:
        return True
    if viewer.logged_in and viewer.user_id == author_id:
        return True
    return kind == 'evidence' and status == 'pending' and 'reviewer' in roles


# ACTIONS (section 7.0) -------------------------------------------------------
@dataclass(frozen=True)
class Target:
    """What an action acts on, with the facts the rules need."""
    dataset: Dataset
    # 'identity' | 'snapshot' | 'evidence' | 'dataset'
    kind: str = 'identity'
    # the record's status, where it has one
    status: Optional[str] = None
    # added_by / recorded_by / created_by of the record
    author_id: Optional[str] = None
    # the identity was ever published (section 3.1.5)
    identity_published: bool = True
    # identity.reserved
    reserved_by: Optional[str] = None
    # the viewer can see the component (for a child: each parent, 8.8)
    readable: bool = True
    # parents of a child whose FIRST snapshot is being published (8.8)
    parent_datasets: Tuple[Dataset, ...] = field(default_factory=tuple)
    # destination of a dataset move
    destination: Optional[Dataset] = None


Rule = Callable[[Viewer, Roles, Target], bool]


def _role(name: str) -> Rule:
    return lambda viewer, roles, target: name in roles


def _author(viewer: Viewer, roles: Roles, target: Target) -> bool:
    return target.author_id is not None and viewer.user_id == target.author_id


def _author_or_moderator(
        viewer: Viewer, roles: Roles, target: Target) -> bool:
    return 'moderator' in roles or _author(viewer, roles, target)


def _unpublished(target: Target) -> bool:
    return target.status not in ('published', 'withdrawn')


def _publish(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """moderator(D); a child's first snapshot also needs moderator of
    every parent's dataset (8.8)."""
    if 'moderator' not in roles:
        return False
    return all('moderator' in dataset_roles(viewer, parent)
               for parent in target.parent_datasets)


def _create(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """contributor(D); a child also needs read access to each parent."""
    return 'contributor' in roles and target.readable


def _geometry_files(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """Geometry files only while the snapshot is not published (6.6)."""
    return _unpublished(target) and \
        _author_or_moderator(viewer, roles, target)


def _add_photo(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """Before publish author / moderator(D); after publish appended by
    contributor(D) (3.2.2)."""
    if _unpublished(target):
        return _author_or_moderator(viewer, roles, target)
    return 'contributor' in roles or 'moderator' in roles


def _remove_photo(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """Before publish author / moderator(D); after publish moderator(D)."""
    if _unpublished(target):
        return _author_or_moderator(viewer, roles, target)
    return 'moderator' in roles


def _delete_record(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """Hard delete only from draft / pending / rejected (I15)."""
    return target.status in DELETABLE_STATUSES and \
        _author_or_moderator(viewer, roles, target)


def _delete_identity(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """Only while nothing of it was ever published (I19); purge: admin."""
    return not target.identity_published and \
        _author_or_moderator(viewer, roles, target)


def _patch_identity(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """moderator(D); while unpublished also its creator (8.9)."""
    if 'moderator' in roles:
        return True
    return not target.identity_published and _author(viewer, roles, target)


def _move_identity(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """moderator of the source and of the destination dataset."""
    if target.destination is None or 'moderator' not in roles:
        return False
    return 'moderator' in dataset_roles(viewer, target.destination)


def _reserve(viewer: Viewer, roles: Roles, target: Target) -> bool:
    return target.readable and not target.reserved_by


def _release(viewer: Viewer, roles: Roles, target: Target) -> bool:
    """The reserving user, or moderator(D)."""
    return 'moderator' in roles or (
        target.reserved_by is not None
        and viewer.user_id == target.reserved_by)


def _nobody(viewer: Viewer, roles: Roles, target: Target) -> bool:
    return False


RULES: Dict[str, Rule] = {
    # creating
    'create_identity': _create,
    'create_snapshot': _create,
    'create_evidence': _create,
    'supersede_snapshot': _role('contributor'),
    'supersede_evidence': _role('contributor'),
    # the author's own drafts (PATCH on a draft: author or moderator, 8.3)
    'edit_draft': _author_or_moderator,
    'submit': _author,
    'resubmit': _author,
    'delete_record': _delete_record,
    # files
    'upload_geometry': _geometry_files,
    'delete_geometry': _geometry_files,
    'add_photo': _add_photo,
    'delete_photo': _remove_photo,
    'add_attachment': _add_photo,         # same rule as photos (7.3)
    'remove_attachment': _remove_photo,
    # moderation
    'publish': _publish,
    'reject': _role('moderator'),
    'withdraw': _role('moderator'),
    'reinstate': _role('moderator'),
    'promote': _role('moderator'),
    'edit_published_metadata': _role('moderator'),
    'edit_valid_time': _role('moderator'),
    # shape_class / complexity / material_class overrides
    'override_derived': _role('moderator'),
    'set_verification': _role('reviewer'),
    # identity lifecycle
    'patch_identity': _patch_identity,
    'delete_identity': _delete_identity,
    'exit': _role('moderator'),
    'reenter': _role('moderator'),
    'withdraw_identity': _role('moderator'),
    'reinstate_identity': _role('moderator'),
    'move_identity': _move_identity,
    'reserve': _reserve,
    'release': _release,
    # datasets
    'manage_members': _role('moderator'),
    'edit_dataset': _role('moderator'),
    # admin only (the admin shortcut in `can` grants them)
    'create_dataset': _nobody,
    'purge': _nobody,
    'redact_actor': _nobody,
    'manage_users': _nobody,
    'manage_materials': _nobody,
    'read_logs': _nobody,
}


def can(viewer: Viewer, action: str, target: Target) -> bool:
    """Whether ``viewer`` may perform ``action`` on ``target`` (7.0)."""
    rule = RULES.get(action)
    if rule is None:
        raise KeyError(f'unknown action: {action!r}')
    if viewer.is_admin:
        return True
    if not viewer.logged_in:
        return False
    return rule(viewer, dataset_roles(viewer, target.dataset), target)
