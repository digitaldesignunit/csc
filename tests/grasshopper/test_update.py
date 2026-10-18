"""The updater installs the shared library next to the UserObjects (decision
8.111): HTTPS, every file checked against the manifest, an atomic rename, the
old package kept until the new one is in place, a development link never
replaced."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import compstub

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'grasshopper_lib' / 'csc_gh'


@pytest.fixture(scope='module')
def up():
    return compstub.load_component('Update').ns


def manifest_of(files, version='261099'):
    return {'version': version, 'files': [
        {'path': name, 'size': len(data),
         'sha256': hashlib.sha256(data).hexdigest()}
        for name, data in sorted(files.items())]}


FILES = {'__init__.py': b"__version__ = '261099'\n", 'build.py': b'X = 1\n'}


def test_the_update_component_sets_no_message_text_itself():
    text = (compstub.SRC / 'DDU_CSC_Update.py').read_text(encoding='utf-8')
    assert 'Component.Message' not in text


# THE MANIFEST ------------------------------------------------------------------
def test_a_manifest_needs_a_version_files_and_checksums(up):
    check = up['check_manifest']
    assert check(manifest_of(FILES))
    for bad in (None, {}, {'version': '1'}, {'version': '1', 'files': []},
                {'version': '1', 'files': [{'path': '../x.py',
                                            'sha256': '0' * 64}]},
                {'version': '1', 'files': [{'path': 'a/b.py',
                                            'sha256': '0' * 64}]},
                {'version': '1', 'files': [{'path': 'build.py',
                                            'sha256': 'zz'}]},
                {'version': '1', 'files': [{'path': 'build.py',
                                            'sha256': '0' * 64}]}):
        with pytest.raises(up['LibraryInstallError']):
            check(bad)


def test_versions_and_servers(up):
    key = up['library_version_key']
    assert key('261005') < key('261005a') < key('261006')
    assert key(None) < key('000001')
    secure = up['secure_server']
    assert secure('https://csc.example.org')
    assert secure('http://localhost:8000') and secure('http://127.0.0.1:8')
    assert secure('http://[::1]:8000')
    assert not secure('http://csc.example.org')
    assert not secure('ftp://localhost') and not secure('')


def test_the_scripts_folder_is_the_one_on_sys_path(up, monkeypatch):
    folder = os.path.join('x', 'McNeel', 'Rhinoceros', '8.0', 'scripts')
    monkeypatch.setattr(sys, 'path', ['/a', folder, '/b'])
    assert up['scripts_folder']() == os.path.normpath(folder)


# THE INSTALL --------------------------------------------------------------------
def reader(files):
    return files.get


def test_a_first_install_writes_the_package(up, tmp_path):
    version = up['install_library'](str(tmp_path), manifest_of(FILES),
                                    reader(FILES))
    assert version == '261099'
    assert sorted(os.listdir(tmp_path)) == ['csc_gh']
    assert (tmp_path / 'csc_gh' / 'build.py').read_bytes() == b'X = 1\n'
    assert up['library_version_of'](str(tmp_path / 'csc_gh')) == '261099'


def test_an_update_replaces_the_old_package_and_leaves_no_backup(up, tmp_path):
    old = tmp_path / 'csc_gh'
    old.mkdir()
    (old / '__init__.py').write_text("__version__ = '261001'\n")
    (old / 'stale.py').write_text('gone = True\n')
    up['install_library'](str(tmp_path), manifest_of(FILES), reader(FILES))
    assert sorted(os.listdir(tmp_path)) == ['csc_gh']
    assert sorted(os.listdir(old)) == ['__init__.py', 'build.py']


def test_a_wrong_checksum_installs_nothing_and_keeps_the_old_package(
        up, tmp_path):
    old = tmp_path / 'csc_gh'
    old.mkdir()
    (old / '__init__.py').write_text("__version__ = '261001'\n")
    tampered = dict(FILES, **{'build.py': b'X = 2\n'})
    with pytest.raises(up['LibraryInstallError']) as info:
        up['install_library'](str(tmp_path), manifest_of(FILES),
                              reader(tampered))
    assert 'checksum' in str(info.value)
    assert up['library_version_of'](str(old)) == '261001'
    assert sorted(os.listdir(tmp_path)) == ['csc_gh']      # no temp folder


def test_a_missing_file_or_a_wrong_version_installs_nothing(up, tmp_path):
    with pytest.raises(up['LibraryInstallError']):
        up['install_library'](str(tmp_path), manifest_of(FILES),
                              reader({'__init__.py': FILES['__init__.py']}))
    with pytest.raises(up['LibraryInstallError']) as info:
        up['install_library'](str(tmp_path),
                              manifest_of(FILES, version='261100'),
                              reader(FILES))
    assert 'version' in str(info.value)
    assert os.listdir(tmp_path) == []


def test_a_failing_rename_puts_the_old_package_back(up, tmp_path,
                                                    monkeypatch):
    old = tmp_path / 'csc_gh'
    old.mkdir()
    (old / '__init__.py').write_text("__version__ = '261001'\n")
    real = os.rename
    calls = []

    def rename(source, target):
        calls.append((source, target))
        if os.path.basename(str(source)).startswith('.csc_gh_new_'):
            raise OSError('locked')                 # the new folder
        return real(source, target)

    monkeypatch.setattr(os, 'rename', rename)
    with pytest.raises(up['LibraryInstallError']):
        up['install_library'](str(tmp_path), manifest_of(FILES),
                              reader(FILES))
    monkeypatch.undo()
    assert up['library_version_of'](str(old)) == '261001'
    assert sorted(os.listdir(tmp_path)) == ['csc_gh']


def test_a_link_to_a_repository_is_never_replaced(tmp_path):
    module = compstub.load_component('Update').ns
    module['is_link'] = lambda path: True           # the module's own name
    with pytest.raises(module['LibraryInstallError']) as info:
        module['install_library'](str(tmp_path), manifest_of(FILES),
                                  reader(FILES))
    assert 'link' in str(info.value)
    assert os.listdir(tmp_path) == []


def test_is_link_is_false_for_a_folder_and_a_missing_path(up, tmp_path):
    assert up['is_link'](str(tmp_path)) is False
    assert up['is_link'](str(tmp_path / 'nothing')) is False


# THE LOCAL CHECKOUT -------------------------------------------------------------
def test_the_package_of_this_checkout_installs_and_imports(up, tmp_path):
    manifest, read = up['local_library_manifest'](str(REPO))
    import csc_gh
    assert manifest['version'] == csc_gh.__version__
    names = {f['path'] for f in manifest['files']}
    assert names == {p.name for p in PACKAGE.glob('*.py')}
    up['install_library'](str(tmp_path), manifest, read)
    code = ('import csc_gh; print(csc_gh.__version__); '
            'import csc_gh.build, csc_gh.ports, csc_gh.messages')
    out = subprocess.run(
        [sys.executable, '-c', code], capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': str(tmp_path)})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == csc_gh.__version__




# THE USER OBJECTS (decision 8.155) -----------------------------------------------
def uo_entry(name, data):
    return {'name': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def uo_manifest(files):
    return {'ref': 'v1', 'version': '1', 'files': [uo_entry(n, d) for n, d in sorted(files.items())]}


UOS = {'DDU_CSC_A': b'ghuser a', 'DDU_CSC_B': b'ghuser b', 'DDU_CSC_C': b'ghuser c'}


def test_a_userobject_manifest_needs_files_names_and_checksums(up):
    check = up['check_userobject_manifest']
    assert check(uo_manifest(UOS))
    entry = uo_entry('DDU_CSC_A', b'x')
    for bad in (None, {}, {'files': []}, {'files': [{**entry, 'name': '../x'}]},
                {'files': [{**entry, 'name': 'a/b'}]}, {'files': [{**entry, 'name': ''}]},
                {'files': [{**entry, 'sha256': 'zz'}]}, {'files': [entry, entry]}):
        with pytest.raises(up['UserObjectError']):
            check(bad)


def test_an_installed_file_with_the_hash_of_the_manifest_is_skipped(up, tmp_path):
    installed = {}
    for name in ('DDU_CSC_A', 'DDU_CSC_B'):
        path = tmp_path / (name + '.ghuser')
        path.write_bytes(UOS[name])
        installed[name] = str(path)
    unchanged, to_fetch = up['plan_userobjects'](uo_manifest(UOS), installed)
    assert unchanged == ['DDU_CSC_A', 'DDU_CSC_B']
    assert [e['name'] for e in to_fetch] == ['DDU_CSC_C']          # missing: downloaded


def test_a_changed_file_is_downloaded_and_an_unreadable_one_too(up, tmp_path):
    changed = tmp_path / 'DDU_CSC_A.ghuser'
    changed.write_bytes(b'an old version')
    unchanged, to_fetch = up['plan_userobjects'](
        uo_manifest({'DDU_CSC_A': UOS['DDU_CSC_A']}),
        {'DDU_CSC_A': str(changed)})
    assert unchanged == [] and [e['name'] for e in to_fetch] == ['DDU_CSC_A']
    gone = up['plan_userobjects'](uo_manifest({'DDU_CSC_A': b'x'}),
                                  {'DDU_CSC_A': str(tmp_path / 'nothing.ghuser')})
    assert [e['name'] for e in gone[1]] == ['DDU_CSC_A']


def test_what_may_not_be_written(up):
    entry = uo_entry('DDU_CSC_A', b'right')
    problem = up['userobject_problem']
    assert problem(entry, b'right') is None
    assert problem(entry, None) == 'download failed'
    assert problem(entry, b'wrong, longer') == 'size mismatch'
    assert problem(entry, b'RIGHT') == 'checksum mismatch'         # same size, other bytes


def test_a_mismatch_keeps_the_old_file_and_the_others_are_written(up, tmp_path):
    old = tmp_path / 'DDU_CSC_B.ghuser'
    old.write_bytes(b'old b')
    entries = [uo_entry(n, d) for n, d in sorted(UOS.items())]
    served = dict(UOS, DDU_CSC_B=b'ghuser X')                      # same size, other bytes
    installed, failed = up['install_userobjects'](
        entries, lambda name: str(tmp_path / (name + '.ghuser')), served.get)
    assert installed == ['DDU_CSC_A', 'DDU_CSC_C']
    assert failed == [('DDU_CSC_B', 'checksum mismatch')]
    assert old.read_bytes() == b'old b'                            # the old file stays
    assert (tmp_path / 'DDU_CSC_A.ghuser').read_bytes() == UOS['DDU_CSC_A']
    assert sorted(os.listdir(tmp_path)) == ['DDU_CSC_A.ghuser', 'DDU_CSC_B.ghuser',
                                            'DDU_CSC_C.ghuser']    # no temporary file


def test_a_failure_does_not_stop_the_run(up, tmp_path):
    entries = [uo_entry(n, d) for n, d in sorted(UOS.items())]

    def read(name):
        if name == 'DDU_CSC_A':
            raise ConnectionError('the connection dropped')
        if name == 'DDU_CSC_B':
            return None                                            # an error answer
        return UOS[name]

    installed, failed = up['install_userobjects'](
        entries, lambda name: str(tmp_path / (name + '.ghuser')), read)
    assert installed == ['DDU_CSC_C']
    assert [n for n, _ in failed] == ['DDU_CSC_A', 'DDU_CSC_B']
    assert 'connection dropped' in failed[0][1] and failed[1][1] == 'download failed'
    assert not (tmp_path / 'DDU_CSC_A.ghuser').exists()


def test_a_write_that_fails_is_a_failed_file_not_a_stop(up, tmp_path):
    entries = [uo_entry(n, d) for n, d in sorted(UOS.items())]
    written = []

    def write(path, data):
        if path.endswith('DDU_CSC_A.ghuser'):
            raise PermissionError('read-only folder')
        written.append(os.path.basename(path))

    installed, failed = up['install_userobjects'](
        entries, lambda name: str(tmp_path / (name + '.ghuser')), UOS.get, write=write)
    assert written == ['DDU_CSC_B.ghuser', 'DDU_CSC_C.ghuser']
    assert installed == ['DDU_CSC_B', 'DDU_CSC_C']
    assert failed[0][0] == 'DDU_CSC_A' and 'read-only folder' in failed[0][1]


def test_a_write_in_one_step_leaves_no_temporary_file_when_it_fails(up, tmp_path, monkeypatch):
    target = tmp_path / 'DDU_CSC_A.ghuser'
    target.write_bytes(b'old')

    def broken(source, destination):
        raise OSError('rename failed')

    monkeypatch.setattr(os, 'replace', broken)
    with pytest.raises(OSError):
        up['write_userobject'](str(target), b'new')
    assert target.read_bytes() == b'old' and os.listdir(tmp_path) == ['DDU_CSC_A.ghuser']


def test_the_state_and_the_texts_after_a_failure(up):
    state = up['update_state']
    assert state([], False, False) == 'Updated'
    assert state([], False, True) == 'Restart Rhino'
    assert state([('A', 'x')], False, True) == 'Update incomplete, run again'
    assert state([], True, False) == 'Update incomplete, run again'
    assert up['STATE_INCOMPLETE'] == 'Update incomplete, run again'
    assert up['userobject_counts_text'](50, 4, 1) == 'UserObjects: 50 installed, 4 unchanged, 1 failed.'
    text = up['failed_userobjects_text']([('DDU_CSC_B', 'checksum mismatch'), ('DDU_CSC_A', 'download failed')])
    assert 'DDU_CSC_B (checksum mismatch), DDU_CSC_A (download failed)' in text


def test_the_local_checkout_has_the_same_manifest(up):
    manifest = up['local_userobject_manifest'](str(REPO))
    folder = REPO / 'grasshopper_userobjects'
    assert {f['name'] for f in manifest['files']} == {p.stem for p in folder.glob('*.ghuser')}
    for entry in manifest['files']:
        data = (folder / (entry['name'] + '.ghuser')).read_bytes()
        assert entry['size'] == len(data) and entry['sha256'] == hashlib.sha256(data).hexdigest()
    up['check_userobject_manifest'](manifest)


def test_the_file_hash_of_a_missing_file_is_none(up, tmp_path):
    assert up['file_sha256'](str(tmp_path / 'nothing')) is None
    path = tmp_path / 'f'
    path.write_bytes(b'abc')
    assert up['file_sha256'](str(path)) == hashlib.sha256(b'abc').hexdigest()


# A SWAPPED SOURCE IS NOT HEALED (decision 8.155) ----------------------------------
class Script:
    """A script component on the canvas: only SetSource and the message are
    there; any other call would be an AttributeError."""

    class RuntimeMessageLevel:
        Remark = 'remark'
        Warning = 'warning'

    def __init__(self):
        self.source, self.messages = None, []

    def SetSource(self, source):
        self.source = source

    def AddRuntimeMessage(self, level, message):
        self.messages.append((level, message))


def test_a_source_swap_sets_the_source_and_a_remark_and_nothing_else():
    module = compstub.load_component('Update')
    obj = compstub.instance(module, 'Update')
    script = Script()
    done = obj.replace_scriptcomp_source(['PY3', 'nick', 'Name', script, 'old'], 'new source',
                                         (261018, 0, 0))
    assert done is True and script.source == 'new source'
    assert script.messages == [('remark', 'Source updated to v261018. Inputs and outputs may have '
                                'changed: open the script editor and click Apply (or paste the '
                                'source again) to update them, then recompute.')]


def test_the_old_components_are_still_reported_not_replaced():
    module = compstub.load_component('Update')
    obj = compstub.instance(module, 'Update')
    for kind in ('GHPY', 'CS'):
        script = Script()
        assert obj.replace_scriptcomp_source([kind, 'n', 'N', script, 'old'], 'x', (1, 0, 0)) is False
        assert script.source is None and script.messages == []


def test_no_self_healing_is_left_in_the_updater():
    text = (compstub.SRC / 'DDU_CSC_Update.py').read_text(encoding='utf-8')
    for gone in ('SetParametersFromScript', 'VariableParameterMaintenance', 'expire_replaced',
                 'ScheduleSolution', 'ExpireSolution', 'TODO: add userobject file version'):
        assert gone not in text, gone
    assert not hasattr(compstub.load_component('Update').CSC_Update, 'expire_replaced')


def test_version_texts_and_the_end_of_run_line(up):
    text = up['version_text']
    assert text((251009, 0, 0)) == '251009' and text((251009, 1, 0)) == '251009.1'
    assert text((251009, 0, 1)) == '251009a' and text((251009, 2, 3)) == '251009.2c'
    assert text(None) == '?'
    assert up['replaced_summary'](['Alpha', 'Beta']) == (
        'Replaced the source of 2 components: Alpha, Beta. Each needs a recompute.')
