# The upload side of the Add components (decisions 8.92, 8.95): the staged
# files of one create, their PUTs, the submit step and the answer texts.
#
# Nothing here imports requests or Rhino: it talks to the Session's
# ``auth_core`` (``authorized_put`` / ``authorized_post`` /
# ``authorized_get``), so the tests drive it with a fake.
#
# Python 3.9 compatible; part of the package csc_gh (decision 8.111).

import json  # NOQA
import os  # NOQA
import platform  # NOQA


def staging_root():
    """Where Create stages the files of a create until Add uploads them."""
    if platform.system() == 'Windows':
        base = os.path.expandvars('%APPDATA%')
        return os.path.join(base, 'DDU_CSC', 'pending_assets')
    return os.path.join(os.path.expanduser('~'), 'Library',
                        'Application Support', 'DDU_CSC', 'pending_assets')


def staging_dir(key, root=None):
    return os.path.join(root or staging_root(), key)


def load_manifest(directory):
    """The staging manifest of a create, or None when nothing was staged."""
    path = os.path.join(directory, 'manifest.json')
    if not os.path.isfile(path):
        return None
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def write_manifest(directory, manifest_dict):
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, 'manifest.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(manifest_dict, handle, indent=2)


LEVELS = ('detailed', 'reduced')


def staged_plan(directory, manifest_dict):
    """The files a create staged: ``(pending, missing)``, each a list of
    ``{kind, index, level, path}`` (kind ``mesh`` / ``point_cloud``). The
    manifest is a file on disk and becomes part of a path and of a URL, so
    only integer indices and the two known levels are followed; anything else
    is reported as missing and never uploaded."""
    pending, missing = [], []
    meshes = (manifest_dict or {}).get('meshes', {})
    for key, levels in sorted(meshes.items(), key=lambda item: str(item[0])):
        for level in levels:
            try:
                index = int(key)
                valid = index >= 0 and level in LEVELS
            except (TypeError, ValueError):
                valid = False
            if not valid:
                missing.append({'kind': 'mesh', 'index': key, 'level': level,
                                'path': '(invalid manifest entry %r/%r)'
                                % (key, level)})
                continue
            path = os.path.join(directory, 'meshes', str(index),
                                level + '.ply')
            entry = {'kind': 'mesh', 'index': index, 'level': level,
                     'path': path}
            (pending if os.path.isfile(path) else missing).append(entry)
    for key in (manifest_dict or {}).get('point_clouds', []):
        try:
            index = int(key)
            valid = index >= 0 and not isinstance(key, bool)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            missing.append({'kind': 'point_cloud', 'index': key,
                            'level': None, 'path':
                            '(invalid manifest entry %r)' % (key,)})
            continue
        path = os.path.join(directory, 'point_clouds', '%d.ply' % index)
        entry = {'kind': 'point_cloud', 'index': index, 'level': None,
                 'path': path}
        (pending if os.path.isfile(path) else missing).append(entry)
    return pending, missing


def upload_path(snapshot_id, entry):
    if entry['kind'] == 'mesh':
        return '/snapshots/%s/meshes/%d/%s' % (
            snapshot_id, entry['index'], entry['level'])
    return '/snapshots/%s/point_clouds/%d.ply' % (snapshot_id, entry['index'])


def http_error_text(response, what='Request'):
    """One readable sentence for an error answer (422 lists the fields)."""
    try:
        body = response.json()
    except Exception:
        return '%s failed (HTTP %s)' % (what, response.status_code)
    detail = body.get('detail', body) if isinstance(body, dict) else body
    lines = []
    if isinstance(detail, dict):
        errors = detail.get('errors') or detail.get('fields')
        if isinstance(errors, list):
            for error in errors:
                if isinstance(error, dict):
                    lines.append('%s: %s' % (
                        error.get('path') or error.get('field') or '?',
                        error.get('message') or error.get('msg') or error))
                else:
                    lines.append(str(error))
        message = detail.get('message')
        if message:
            lines.insert(0, str(message))
        if not lines:
            lines.append(json.dumps(detail))
    elif isinstance(detail, list):
        for error in detail:
            if isinstance(error, dict):
                where = '.'.join(str(p) for p in (error.get('loc') or [])
                                 if p not in ('body',)) or '?'
                lines.append('%s: %s' % (where, error.get('msg')))
            else:
                lines.append(str(error))
    else:
        lines.append(str(detail))
    return '%s failed (HTTP %s):\n%s' % (what, response.status_code,
                                         '\n'.join(lines))


def upload_staged(auth_core, snapshot_id, entries, progress=None):
    """PUT every staged file of a snapshot over the Session's connection.

    ``progress(text)`` is told what is under way. Returns ``(done, failed)``
    with ``failed`` a list of ``(entry, reason)``.
    """
    done, failed = [], []
    for entry in entries:
        name = os.path.basename(entry['path'])
        if progress:
            progress('Uploading %s %d (%s)...' % (
                entry['kind'].replace('_', ' '), entry['index'],
                entry['level'] or 'original'))
        field = 'mesh_file' if entry['kind'] == 'mesh' else \
            'point_cloud_file'
        try:
            with open(entry['path'], 'rb') as handle:
                response = auth_core.authorized_put(
                    upload_path(snapshot_id, entry),
                    files={field: (name, handle,
                                   'application/octet-stream')},
                    timeout=300)
        except OSError as error:
            failed.append((entry, 'cannot read %s: %s' % (name, error)))
            continue
        if response.status_code == 200:
            done.append(entry)
        else:
            failed.append((entry, http_error_text(response, 'Upload of ' +
                                                  name)))
    return done, failed


def passport_after(auth_core, identity_doc, snapshot_doc):
    """``{identity, snapshots:[snapshot]}`` as the server now has it (the
    snapshot by id), else assembled from the documents at hand."""
    identity_id = (identity_doc or {}).get('_id')
    snapshot_id = (snapshot_doc or {}).get('_id')
    if identity_id and snapshot_id:
        try:
            response = auth_core.authorized_get(
                '/identities/%s/compose' % identity_id,
                params={'snapshots': snapshot_id})
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
    return {'identity': identity_doc or {}, 'snapshots': [snapshot_doc or {}]}


def clear_staging(root=None):
    """Remove everything staged (not the Session's cache); returns the
    folder that was cleared."""
    import shutil
    root = root or staging_root()
    if os.path.isdir(root):
        shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)
    return root


def commit_staging(tmp_dir, key, manifest_dict, root=None):
    """Move the staged files of a create from their temporary folder to the
    folder named by ``key`` (replacing an older one) and write the manifest.
    Returns the folder, or None when no file was staged."""
    import shutil
    has_files = bool(manifest_dict.get('meshes')
                     or manifest_dict.get('point_clouds'))
    final = staging_dir(key, root)
    if os.path.isdir(final):
        shutil.rmtree(final, ignore_errors=True)
    if not has_files:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None
    os.makedirs(os.path.dirname(final), exist_ok=True)
    os.replace(tmp_dir, final)
    write_manifest(final, manifest_dict)
    return final
