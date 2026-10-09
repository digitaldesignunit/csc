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


# THE SWAPPED COMPONENTS ARE SOLVED AGAIN -----------------------------------------
def test_replaced_components_are_expired_between_solutions():
    module = compstub.load_component('Update')
    scheduled = []
    document = type('Doc', (), {
        'ScheduleSolution': lambda self, ms, callback: scheduled.append(
            callback)})()
    module.ns['ghenv'].Component.OnPingDocument = lambda: document
    obj = compstub.instance(module, 'Update')

    class Swapped:
        expired = []

        def ExpireSolution(self, recompute):
            self.expired.append(recompute)

    first, second = Swapped(), Swapped()
    first.expired, second.expired = [], []
    obj.expire_replaced([])
    assert scheduled == []                         # nothing swapped
    obj.expire_replaced([first, second])
    assert len(scheduled) == 1 and first.expired == []   # not inside the run
    scheduled[0](document)
    assert first.expired == [False] and second.expired == [False]
