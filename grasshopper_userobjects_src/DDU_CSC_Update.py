#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import hashlib  # NOQA
import os  # NOQA
import re  # NOQA
import glob  # NOQA
import shutil  # NOQA
import stat  # NOQA
import sys  # NOQA
import uuid  # NOQA
from pathlib import Path  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA
import GhPython as ghpy  # NOQA
import ScriptComponents as scomp  # NOQA
import RhinoCodePluginGH as rcpgh  # NOQA

# the one place that sets the text under the component (decision 8.113); the
# updater installs the library, so it must work without it
try:
    from csc_gh.messages import set_state
except ImportError:
    set_state = None

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'Update'  # NOQA
ghenv.Component.NickName = 'CSC_Update'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '0 Development'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Updates component sources, userobjects and the shared library '
    'csc_gh (installed to the Rhino scripts folder) from server.\n'
    'NOTE: CheckForUpdates must be True to check for updates AND to '
    'install updates! Switch on both to update everything.\n'
    'Updates come from the Grasshopper release that belongs to the '
    'server. UPDATE_CHANNEL (empty by default) may name a GitHub branch or '
    'tag for testing; it must match the remote name exactly.'
)

# Leave empty: the server then delivers the UserObjects of the release it runs
# (tag v<version>), so an update always matches the backend. Testers may set a
# GitHub branch or tag here; it must match the remote name exactly.
UPDATE_CHANNEL = ''

# Matches an actual version declaration - the word "version", a ":" or "=",
# then the number. The separator is required so prose such as 'creates a
# version-0 snapshot' in a component description cannot be mistaken for a
# version declaration. Keep this comment free of literal declarations, they
# would be picked up before the real one below.
VERSION_DECLARATION_RE = re.compile(
    r'version\s*[:=]\s*(\d+(?:\.\d+)?[a-zA-Z]?)')

# Components that were renamed or split. Their sources no longer exist on the
# server, so they can only be reported - not updated in place.
RENAMED_COMPONENTS = {
    'AddComponent': 'AddComponentIdentity',
    'ArrangeComponents': 'CreateArrangement',
    'CreateComponent': 'CreateComponentIdentity / CreateComponentSnapshot',
    'FetchGeometry': 'FetchReducedGeometry / FetchOriginalGeometry',
    'FetchDetailedGeometry': 'FetchOriginalGeometry',
    'ApplyPCAFrame': 'ApplyFrame',
    'CreateReinforcement': 'ReinforcementLayout',
}

# Components that were removed in 0.6 without a successor: designs are not
# part of CSC any more (decision 7.11).
REMOVED_COMPONENTS = {
    'CreateDesign': 'removed in 0.6: designs are not part of CSC',
    'AddDesign': 'removed in 0.6: designs are not part of CSC',
    'FetchDesign': 'removed in 0.6: designs are not part of CSC',
}

# THE SHARED LIBRARY csc_gh (decision 8.111) ------------------------------------
LIBRARY_NAME = 'csc_gh'
LIBRARY_VERSION_RE = re.compile(r"^__version__\s*=\s*'(\d+[a-zA-Z]?)'\s*$",
                                re.M)
LIBRARY_FILE_RE = re.compile(r'^(__init__|[a-z][a-z_]*)\.py$')


class LibraryInstallError(Exception):
    """The library was not installed; the old one is untouched."""


def scripts_folder():
    """Rhino 8's scripts folder (on sys.path of every Python 3 script): the
    entry of sys.path that ends in McNeel/Rhinoceros/8.0/scripts, else the
    default place of the platform."""
    for entry in sys.path:
        parts = os.path.normpath(entry).replace('\\', '/').split('/')
        if parts[-4:] == ['McNeel', 'Rhinoceros', '8.0', 'scripts']:
            return os.path.normpath(entry)
    if sys.platform.startswith('win'):
        base = os.path.expandvars('%APPDATA%')
        return os.path.join(base, 'McNeel', 'Rhinoceros', '8.0', 'scripts')
    return os.path.join(os.path.expanduser('~'), 'Library',
                        'Application Support', 'McNeel', 'Rhinoceros',
                        '8.0', 'scripts')


def is_link(path):
    """A symbolic link or a directory junction (the development setup of
    grasshopper_development/README.md): never replaced by an update."""
    try:
        if os.path.islink(path):
            return True
        attributes = getattr(os.lstat(path), 'st_file_attributes', 0)
        return bool(attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT',
                                         0x400))
    except OSError:
        return False


def library_version_of(folder):
    """The __version__ text of an installed package folder, else None."""
    try:
        with open(os.path.join(folder, '__init__.py'), 'r',
                  encoding='utf-8') as handle:
            match = LIBRARY_VERSION_RE.search(handle.read())
    except OSError:
        return None
    return match.group(1) if match else None


def library_version_key(version):
    match = re.match(r'^(\d+)([a-zA-Z]?)$', str(version or ''))
    if not match:
        return (-1, '')
    return (int(match.group(1)), match.group(2).lower())


def secure_server(base_url):
    """HTTPS, or the loopback address of a local development server."""
    url = (base_url or '').lower()
    if url.startswith('https://'):
        return True
    host = url.split('://', 1)[-1].split('/')[0]
    if host.startswith('['):
        host = host.split(']')[0] + ']'
    else:
        host = host.split(':')[0]
    return url.startswith('http://') and host in (
        'localhost', '127.0.0.1', '[::1]')


def check_manifest(manifest):
    """The manifest as the installer takes it: a version, and per file a plain
    name of the package and a sha256; raises LibraryInstallError."""
    if not isinstance(manifest, dict) or not manifest.get('version'):
        raise LibraryInstallError('the library manifest has no version')
    files = manifest.get('files')
    if not files:
        raise LibraryInstallError('the library manifest lists no files')
    names = set()
    for entry in files:
        name = str(entry.get('path', ''))
        if not LIBRARY_FILE_RE.match(name) or name in names:
            raise LibraryInstallError('not a library file name: %r' % name)
        if not re.match(r'^[0-9a-f]{64}$', str(entry.get('sha256', ''))):
            raise LibraryInstallError('no sha256 for %s' % name)
        names.add(name)
    if '__init__.py' not in names:
        raise LibraryInstallError('the manifest has no __init__.py')
    return manifest


def install_library(scripts_dir, manifest, read_file):
    """Install the package ``csc_gh`` into ``scripts_dir``.

    ``manifest`` is the release manifest ({version, files: [{path, size,
    sha256}]}); ``read_file(name)`` returns the bytes of one file. Every file
    is checked against the manifest (size, sha256) and written into a
    temporary folder next to the target; the installed package is renamed to
    ``csc_gh.bak``, the new folder to ``csc_gh`` and the backup removed. Any
    failure leaves the old package in place (the backup is put back).
    Raises LibraryInstallError; returns the installed version."""
    check_manifest(manifest)
    target = os.path.join(scripts_dir, LIBRARY_NAME)
    if is_link(target):
        raise LibraryInstallError(
            '%s is a link to a repository (a development setup): not '
            'replaced' % target)
    os.makedirs(scripts_dir, exist_ok=True)
    fresh = os.path.join(scripts_dir, '.%s_new_%s' % (LIBRARY_NAME,
                                                      uuid.uuid4().hex[:8]))
    backup = target + '.bak'
    os.makedirs(fresh)
    try:
        for entry in manifest['files']:
            data = read_file(entry['path'])
            if data is None:
                raise LibraryInstallError('missing: %s' % entry['path'])
            if hashlib.sha256(data).hexdigest() != entry['sha256'] or (
                    'size' in entry and len(data) != entry['size']):
                raise LibraryInstallError(
                    'checksum mismatch: %s (not installed)' % entry['path'])
            with open(os.path.join(fresh, entry['path']), 'wb') as handle:
                handle.write(data)
        if library_version_of(fresh) != str(manifest['version']):
            raise LibraryInstallError('the files are not version %s'
                                      % manifest['version'])
        if os.path.exists(backup):
            shutil.rmtree(backup)
        had_old = os.path.isdir(target)
        if had_old:
            os.rename(target, backup)
        try:
            os.rename(fresh, target)
        except OSError:
            if had_old:
                os.rename(backup, target)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    except LibraryInstallError:
        shutil.rmtree(fresh, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(fresh, ignore_errors=True)
        raise LibraryInstallError('%s' % error) from error
    return str(manifest['version'])


def local_library_manifest(root, folder_name='grasshopper_lib'):
    """The manifest of the package in a local checkout, and a reader."""
    folder = os.path.join(root, folder_name, LIBRARY_NAME)
    files, data = [], {}
    for name in sorted(os.listdir(folder)):
        if not LIBRARY_FILE_RE.match(name):
            continue
        with open(os.path.join(folder, name), 'rb') as handle:
            data[name] = handle.read()
        files.append({'path': name, 'size': len(data[name]),
                      'sha256': hashlib.sha256(data[name]).hexdigest()})
    init = data.get('__init__.py', b'').decode('utf-8', 'replace')
    match = LIBRARY_VERSION_RE.search(init)
    return ({'ref': 'local', 'version': match.group(1) if match else None,
             'files': files}, data.get)


# The two folders of the repository the updater reads from a local copy
# (decision 8.93: the bridge is tested against a local checkout).
SRC_DIR_NAME = 'grasshopper_userobjects_src'
UO_DIR_NAME = 'grasshopper_userobjects'


class CSC_Update(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output
        # root of a local checkout while LocalFolder is set, else None
        self.local_root = None
        self._local_error = ''

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'Toggle to check for updates on the server.'
        )
        if len(self.InputParams) > 2:
            self.InputParams[2].Description = (
                'Optional: a local copy of the repository (or its '
                'grasshopper_userobjects_src / grasshopper_userobjects '
                'folder). When set, sources and UserObjects are read from '
                'disk instead of the server and no sign-in is needed.'
            )
        self.InputParams[1].Description = (
            'Toggle to install updates from server.'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Status messages about the update process.'
        )

    def _state(self, text=''):
        """The one short state under the component (decision 8.113)."""
        if set_state is not None:
            set_state(self.Component, text)

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            # nothing to check against yet: a warning, not a failure
            self._addWarning('No authentication found. Please use the '
                             'CSC_Session component first.')
            return None
        return auth_core

    # THE LIBRARY (8.111) ---------------------------------------------------
    def expire_replaced(self, objects):
        """Solve the components whose code was replaced. The swap alone does
        not run them, and a component with declared outputs sets them up in its
        first solve (decision 8.112): schedule an expire, which runs between
        solutions."""
        document = self.Component.OnPingDocument()
        if not objects or document is None:
            return

        def callback(_document):
            for obj in objects:
                try:
                    obj.ExpireSolution(False)
                except Exception as error:
                    print(f'Could not expire {obj}: {error}')

        document.ScheduleSolution(
            1, Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(callback))

    def get_api_library_manifest(self, auth_core):
        response = auth_core.authorized_get(
            '/ghinterface/library_manifest', params=self._channel_params(),
            timeout=90)
        if response.status_code != 200:
            raise LibraryInstallError(
                f'the server answered {response.status_code} for the '
                'library manifest')
        return response.json()

    def api_library_reader(self, auth_core):
        def read(name):
            response = auth_core.authorized_get(
                '/ghinterface/library/' + name,
                params=self._channel_params(), timeout=90)
            return response.content if response.status_code == 200 else None
        return read

    def check_library(self, auth_core):
        """What this machine and the release have of csc_gh:
        ``{text, install, manifest, reader, scripts_dir}``; ``install`` says
        whether InstallUpdates would install it."""
        scripts_dir = scripts_folder()
        target = os.path.join(scripts_dir, LIBRARY_NAME)
        result = {'text': '', 'install': False, 'manifest': None,
                  'reader': None, 'scripts_dir': scripts_dir}
        installed = library_version_of(target)
        try:
            if self.local_root:
                manifest, reader = local_library_manifest(self.local_root)
            elif not secure_server(auth_core.base_url):
                result['text'] = (
                    'csc_gh not checked: the server address is not HTTPS')
                self._addWarning(result['text'])
                return result
            else:
                manifest = self.get_api_library_manifest(auth_core)
                reader = self.api_library_reader(auth_core)
            check_manifest(manifest)
        except Exception as error:
            result['text'] = f'csc_gh not checked: {error}'
            self._addWarning(result['text'])
            return result
        wanted = str(manifest['version'])
        if is_link(target):
            result['text'] = (
                f'csc_gh {installed} is linked to a repository (development '
                'setup): not replaced')
            self._addRemark(result['text'])
            return result
        if installed is None:
            result['text'] = f'csc_gh is not installed; release has {wanted}'
        elif library_version_key(installed) < library_version_key(wanted):
            result['text'] = f'csc_gh {installed} < {wanted}: update'
        elif library_version_key(installed) > library_version_key(wanted):
            result['text'] = (
                f'csc_gh {installed} > {wanted} of the release: not '
                'replaced (a development copy?)')
            self._addWarning(result['text'])
            return result
        else:
            result['text'] = f'csc_gh {installed} is up to date'
            self._addRemark(result['text'])
            return result
        result.update(install=True, manifest=manifest, reader=reader)
        self._addRemark(result['text'])
        return result

    def install_library_now(self, library, Status):
        """Install the package; True when it was replaced (Rhino must be
        restarted: imported modules stay cached)."""
        try:
            version = install_library(library['scripts_dir'],
                                      library['manifest'], library['reader'])
        except LibraryInstallError as error:
            msg = f'csc_gh was not installed: {error}'
            self._addError(msg)
            Status.Add(msg)
            return False
        msg = (f'Installed csc_gh {version} to {library["scripts_dir"]}. '
               'Restart Rhino to use it.')
        self._addRemark(msg)
        Status.Add(msg)
        return True

    def _channel_params(self):
        """Query params selecting the GitHub update channel (branch)."""
        return {'channel': UPDATE_CHANNEL} if UPDATE_CHANNEL else {}

    def get_source_version(self, source):
        """
        Attempts to find the first version declaration in a multi line string,
        i.e. the word "version" (or, "Version") followed by ":" or "=" and a
        version number. Lines that merely mention the word "version" are
        ignored.
        Supports formats like:
            Version: 160121
            Version: 251009.1
            Version: 251009a
        """
        for line in source.lower().split('\n'):
            version_match = VERSION_DECLARATION_RE.search(line)
            if version_match:
                return self.parse_version_string(version_match.group(1))
        return None

    def parse_version_string(self, version_str):
        """
        Parse a version string into a comparable format.
        Handles formats like: 251009, 251009.1, 251009a

        Returns a tuple that can be used for comparison:
        - (251009,) for "251009"
        - (251009, 1) for "251009.1"
        - (251009, 0, 'a') for "251009a"
        """
        # Split into base number and suffix
        match = re.match(r'(\d+)(?:\.(\d+))?([a-zA-Z]*)', version_str)
        if not match:
            return None

        base_num = int(match.group(1))
        dot_num = int(match.group(2)) if match.group(2) else 0
        letter_suffix = match.group(3).lower() if match.group(3) else ''

        # Convert letter to number for comparison (a=1, b=2, etc.)
        letter_num = ord(letter_suffix) - ord('a') + 1 if letter_suffix else 0

        return (base_num, dot_num, letter_num)

    def compare_versions(self, version1, version2):
        """
        Compare two version tuples.

        Returns:
            -1 if version1 < version2
             0 if version1 == version2
             1 if version1 > version2
        """
        if version1 is None and version2 is None:
            return 0
        if version1 is None:
            return -1
        if version2 is None:
            return 1

        # Compare tuple elements in order
        for i in range(max(len(version1), len(version2))):
            v1_elem = version1[i] if i < len(version1) else 0
            v2_elem = version2[i] if i < len(version2) else 0

            if v1_elem < v2_elem:
                return -1
            elif v1_elem > v2_elem:
                return 1

        return 0

    def expand_path(self, path):
        """
        Expand environment variables in a path string.
        Handles %APPDATA%, %USERPROFILE%, %TEMP%, etc.
        """
        if not path:
            return path
        return os.path.expandvars(path)

    def replace_scriptcomp_source(
            self, old_script_comp_values, new_source):
        """
        Replaces source code of gh scriptable components.
        """
        # extract data
        script_type, nickname, name, obj, source = old_script_comp_values
        # check for type and decide action
        if (script_type == "PY3" or
                script_type == 'IPY2' or
                script_type == 'CS9'):
            # set the source code
            obj.SetSource(new_source)
            # infer component param inputs from RunScript signature
            obj.SetParametersFromScript()
            # call parameter maintenance helper
            obj.VariableParameterMaintenance()
            rml = obj.RuntimeMessageLevel.Warning
            msg = 'My source just got replaced with a new version!'
            obj.AddRuntimeMessage(rml, msg)
        elif script_type == 'GHPY':
            return False
        elif script_type == 'CS':
            return False
        return True

    def process_document_objects(self, ghdocument, verbose=False):
        """
        Processes GH_Document object and return a list of all script components
        """
        # get all document objects
        comps = list(ghdocument.Objects)

        # types of python components
        ghpycomp = ghpy.Component.ZuiPythonComponent
        ipycomp = rcpgh.Components.IronPython2Component
        py3comp = rcpgh.Components.Python3Component

        # types of csharp components
        cscomp = scomp.Component_CSNET_Script
        cs9comp = rcpgh.Components.CSharpComponent

        # cluster component
        clustercomp = Grasshopper.Kernel.Special.GH_Cluster

        # extract component type strings
        ghpycomp_str = str(ghpycomp).split("'")[1]
        cscomp_str = str(cscomp).split("'")[1]
        ipycomp_str = str(ipycomp).split("'")[1]
        py3comp_str = str(py3comp).split("'")[1]
        cs9comp_str = str(cs9comp).split("'")[1]
        clustercomp_str = str(clustercomp).split("'")[1]

        # define script types
        id_ghpycomp = 'GHPY'
        id_cscomp = 'CS'
        id_ipycomp = 'IPY2'
        id_py3comp = 'PY3'
        id_cs9comp = 'CS9'

        # init dict for script component storage
        script_components = {}

        # loop over all document components
        # store all component objects in a dictionary to check
        # - are all "same" scripts the same code?
        # - are there scripts without category or version attribute?
        # - separate old from new scripts, dont export old scripts!
        for obj in comps:
            # extract basic info
            name = obj.Name
            nickname = obj.NickName
            iguid = str(obj.InstanceGuid)
            # extract type string
            objtype_str = str(obj.GetType())
            # OLD GHPYTHON COMPONENT
            if objtype_str == ghpycomp_str:
                source = obj.Code
                if source:
                    if verbose:
                        print(
                            (f'Found Source for OLD GHPY Component '
                             f'"{nickname}" ({iguid})'))
                    scriptcomp = [id_ghpycomp, nickname, name, obj, source]
                    script_components[iguid] = scriptcomp
            # OLD C# COMPONENT
            elif objtype_str == cscomp_str:
                source = obj.ScriptSource.ScriptCode
                if source:
                    if verbose:
                        print(
                            (f'Found Source for OLD CS Component "{nickname}" '
                             f'({iguid})'))
                    scriptcomp = [id_cscomp, nickname, name, obj, source]
                    script_components[iguid] = scriptcomp
            # NEW C#9 COMPONENT
            elif objtype_str == cs9comp_str:
                bres, source = obj.TryGetSource()
                if bres:
                    if verbose:
                        print((f'Found Source for CS9 Component "{nickname}" '
                               f'({iguid})'))
                    scriptcomp = [id_cs9comp, nickname, name, obj, source]
                    script_components[iguid] = scriptcomp
            # NEW IRONPYTHON COMPONENT
            elif objtype_str == ipycomp_str:
                bres, source = obj.TryGetSource()
                if bres:
                    if verbose:
                        print((f'Found Source for IPY2 Component "{nickname}" '
                               f'({iguid})'))
                    scriptcomp = [id_ipycomp, nickname, name, obj, source]
                    script_components[iguid] = scriptcomp
            # NEW PYTHON3 COMPONENT
            elif objtype_str == py3comp_str:
                bres, source = obj.TryGetSource()
                if bres:
                    if verbose:
                        print((f'Found Source for PY3 Component "{nickname}" '
                               f'({iguid})'))
                    scriptcomp = [id_py3comp, nickname, name, obj, source]
                    script_components[iguid] = scriptcomp
            # CLUSTER COMPONENT
            elif objtype_str == clustercomp_str:
                # RECURSIVELY STEP THROUGH CLUSTERS AND LOOK FOR SCRIPTS ...
                if verbose:
                    print((f'Processing CLUSTER "{nickname}" ({name}, '
                           f'{iguid}) ...'))
                cluster_scripts = self.process_document_objects(
                    obj.Document(''), verbose=verbose
                )
                # add cluster script dict to main dict
                script_components.update(cluster_scripts)
        # return results
        return script_components

    def process_script_components(
            self,
            script_components: dict,
            set_category: str):
        """
        Process found script components and get matching components.
        """
        versioned_script_components = []
        for iguid, values in script_components.items():
            # extract data from dict object
            script_type, nickname, name, obj, source = values
            category = obj.Category
            version = self.get_source_version(source)
            category_match = category == set_category
            version_present = version is not None
            if category_match and version_present:
                versioned_script_components.append((iguid, values))
        return versioned_script_components

    def get_userobjects_dir(self):
        """Get platform-specific UserObjects directory."""
        dir = Grasshopper.Folders.DefaultUserObjectFolder
        return dir

    def resolve_local_root(self, value):
        """The checkout a LocalFolder input names: its root, None for an
        empty input, False (with an error) when it is not a checkout."""
        value = (value or '').strip()
        if not value:
            return None
        root = os.path.abspath(os.path.expanduser(value))
        if os.path.basename(root) in (SRC_DIR_NAME, UO_DIR_NAME):
            root = os.path.dirname(root)
        for name in (SRC_DIR_NAME, UO_DIR_NAME):
            if not os.path.isdir(os.path.join(root, name)):
                msg = (f'LocalFolder {root} has no {name} folder: give the '
                       'root of a CSC checkout.')
                self._addError(msg)
                self._local_error = msg
                return False
        return root

    def local_source_versions(self):
        """{source name: version} of the sources in the local checkout."""
        versions = {}
        folder = os.path.join(self.local_root, SRC_DIR_NAME)
        for file_name in sorted(os.listdir(folder)):
            stem, ext = os.path.splitext(file_name)
            if ext.lower() not in ('.py', '.cs'):
                continue
            with open(os.path.join(folder, file_name), 'r',
                      encoding='utf-8', errors='replace') as handle:
                version = self.get_source_version(handle.read())
            if not version:
                print(f'{stem} has no version, skipping!')
                continue
            versions[stem] = tuple(version)
        return versions

    def local_source_file_text(self, full_name):
        folder = os.path.join(self.local_root, SRC_DIR_NAME)
        for ext in ('.py', '.cs'):
            path = os.path.join(folder, full_name + ext)
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8',
                          errors='replace') as handle:
                    return handle.read()
        msg = f'Source file {full_name} not found in {folder}.'
        self._addError(msg)
        return None

    def local_userobject_names(self):
        folder = os.path.join(self.local_root, UO_DIR_NAME)
        return sorted(os.path.splitext(n)[0] for n in os.listdir(folder)
                      if n.lower().endswith('.ghuser'))

    def local_userobject_bytes(self, uo_name):
        path = os.path.join(self.local_root, UO_DIR_NAME, uo_name + '.ghuser')
        if not os.path.isfile(path):
            msg = f'UserObject {uo_name} not found in {os.path.dirname(path)}.'
            self._addError(msg)
            return None
        with open(path, 'rb') as handle:
            return handle.read()

    def get_api_source_versions(self, auth_core):
        """Get source versions from API (or the local checkout)."""
        if self.local_root:
            return self.local_source_versions()
        api_src_versions = {}
        response = auth_core.authorized_get(
            '/ghinterface/src_names',
            params=self._channel_params(),
            timeout=90
        )
        if response.status_code == 200:
            api_src_files_json = response.json()
            for file_tuple in api_src_files_json:
                name = file_tuple[0]
                version = file_tuple[1]
                if not version:
                    # Source file without a version declaration. Skip it
                    # instead of failing the whole update check.
                    print(f'{name} has no version on server, skipping!')
                    continue
                api_src_versions[name] = tuple(version)
        elif response.status_code == 404:
            msg = (
                f'Update channel "{UPDATE_CHANNEL or "server release"}" was '
                'not found on GitHub. A branch or tag name must match '
                'exactly; the server release exists once it is published.'
            )
            self._addError(msg)
            return None
        elif response.status_code == 401:
            msg = 'Authentication failed. Please sign in again.'
            self._addError(msg)
            return None
        elif response.status_code == 403:
            msg = 'Access denied. Insufficient permissions.'
            self._addError(msg)
            return None
        elif response.status_code == 500:
            msg = 'Server error. Please try again later.'
            self._addError(msg)
            return None
        else:
            msg = (f'Request failed with status code: '
                   f'{response.status_code}')
            try:
                detail = response.json().get('detail')
                if detail:
                    msg = f'{msg}: {detail}'
            except Exception:
                pass
            self._addError(msg)
            return None
        return api_src_versions

    def get_api_userobject_names(self, auth_core):
        """Get userobject names from API (or the local checkout)."""
        if self.local_root:
            return self.local_userobject_names()
        api_uo_names = []
        response = auth_core.authorized_get(
            '/ghinterface/userobject_names',
            params=self._channel_params(),
            timeout=60
        )
        if response.status_code == 200:
            api_uo_names = list(response.json())
        elif response.status_code == 404:
            msg = (
                f'Update channel "{UPDATE_CHANNEL or "server release"}" was '
                'not found on GitHub. A branch or tag name must match '
                'exactly; the server release exists once it is published.'
            )
            self._addError(msg)
            return None
        elif response.status_code == 401:
            msg = 'Authentication failed. Please sign in again.'
            self._addError(msg)
            return None
        elif response.status_code == 403:
            msg = 'Access denied. Insufficient permissions.'
            self._addError(msg)
            return None
        elif response.status_code == 500:
            msg = 'Server error. Please try again later.'
            self._addError(msg)
            return None
        else:
            msg = (f'Request failed with status code: '
                   f'{response.status_code}')
            self._addError(msg)
            return None
        return api_uo_names

    def get_api_source_file_text(self, auth_core, full_name):
        """Get source file from API (or the local checkout)."""
        if self.local_root:
            return self.local_source_file_text(full_name)
        response = auth_core.authorized_get(
            f'/ghinterface/src/{full_name}',
            params=self._channel_params(),
            timeout=60
        )
        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            msg = 'Source file not found.'
            self._addError(msg)
            return None
        elif response.status_code == 401:
            msg = 'Authentication failed. Please sign in again.'
            self._addError(msg)
            return None
        elif response.status_code == 403:
            msg = 'Access denied. Insufficient permissions.'
            self._addError(msg)
            return None
        elif response.status_code == 500:
            msg = 'Server error. Please try again later.'
            self._addError(msg)
            return None
        else:
            msg = (f'Request failed with status code: '
                   f'{response.status_code}')
            self._addError(msg)
            return None

    def get_api_userobject_bytes(self, auth_core, uo_name):
        """Get userobject bytes from API (or the local checkout)."""
        if self.local_root:
            return self.local_userobject_bytes(uo_name)
        response = auth_core.authorized_get(
            f'/ghinterface/userobject/{uo_name}',
            params=self._channel_params(),
            timeout=60
        )
        if response.status_code == 200:
            return response.content
        elif response.status_code == 404:
            msg = 'Userobject not found.'
            self._addError(msg)
            return None
        elif response.status_code == 401:
            msg = 'Authentication failed. Please sign in again.'
            self._addError(msg)
            return None
        elif response.status_code == 403:
            msg = 'Access denied. Insufficient permissions.'
            self._addError(msg)
            return None
        elif response.status_code == 500:
            msg = 'Server error. Please try again later.'
            self._addError(msg)
            return None
        else:
            msg = (f'Request failed with status code: '
                   f'{response.status_code}')
            self._addError(msg)
            return None

    def RunScript(self,
            CheckForUpdates: bool,
            InstallUpdates: bool,
            LocalFolder: str):
        if not LocalFolder or LocalFolder == '':
            LocalFolder = None
        # hardcoded category of the components to update
        CATEGORY = 'DDU_CSC'
        # init output tree for status messages
        Status = Grasshopper.DataTree[System.Object]()
        # a local checkout replaces the server (no sign-in needed)
        local_root = self.resolve_local_root(LocalFolder)
        if local_root is False:
            Status.Add(self._local_error)
            return Status
        self.local_root = local_root
        # Get AuthCore instance from sticky storage
        auth_core = None if self.local_root else \
            self.get_auth_core_from_sticky()
        if auth_core is None and not self.local_root:
            return Status
        if UPDATE_CHANNEL and not self.local_root:
            channel_msg = (
                f'UPDATE_CHANNEL is "{UPDATE_CHANNEL}" instead of the '
                "server's release. It must match a GitHub branch or tag "
                'exactly.'
            )
            self._addWarning(channel_msg)
            Status.Add(channel_msg)
        # Check if authentication is valid
        if not self.local_root and not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addWarning(msg)
            Status.Add(msg)
            return Status
        msg = (
            'Toggle CheckForUpdates to True to check for updates on the '
            'server.'
        )
        try:
            if CheckForUpdates:
                msg = (
                    f'Using the local checkout {self.local_root}'
                    if self.local_root else
                    f'Using GitHub update channel: {UPDATE_CHANNEL}'
                    if UPDATE_CHANNEL else
                    "Using the Grasshopper release that belongs to the "
                    'server'
                )
                self._addRemark(msg)
                Status.Add(msg)
                msg = (
                    f'Searching current document for {CATEGORY} script '
                    'components...'
                )
                # loop through the document to find all script components
                doc = self.Component.OnPingDocument()
                script_components = self.process_script_components(
                    self.process_document_objects(doc),
                    CATEGORY
                )
                msg = (
                    f'Found {len(script_components)} {CATEGORY} script '
                    'components in current document (including duplicates).'
                )
                self._addRemark(msg)
                Status.Add(msg)
                # make request to fetch all source file names and versions
                msg = (
                    f'Checking Server for updates '
                    f'(channel: {UPDATE_CHANNEL or "server release"})...'
                )
                api_src_versions = self.get_api_source_versions(auth_core)
                if api_src_versions is None:
                    msg = 'Failed to get source versions from server.'
                    self._addError(msg)
                    Status.Add(msg)
                    return Status
                msg = (f'Found {len(api_src_versions)} unique script '
                       'component source files on server.')
                self._addRemark(msg)
                Status.Add(msg)

                # loop over scripts in document
                scripts_to_update = []
                unmatched_names = []
                for iguid, values in script_components:
                    script_type, nickname, name, obj, current_source = values
                    current_version = self.get_source_version(current_source)
                    full_name = CATEGORY + '_' + name
                    if full_name not in api_src_versions:
                        print(f'{full_name} not found on server!')
                        if name not in unmatched_names:
                            unmatched_names.append(name)
                        continue
                    api_version = api_src_versions[full_name]
                    vc = self.compare_versions(
                        api_version,
                        current_version
                    )
                    if vc == -1:
                        print(
                            f'!! --> {name} {api_version} '
                            f'< {current_version}!'
                        )
                        msg = (
                            f'{name} {api_version} < {current_version}! '
                            'Is this a dev file? That should '
                            'not happen otherwise! Proceed with caution!'
                        )
                        self._addWarning(msg)
                        Status.Add(msg)
                        continue
                    elif vc == 0:
                        print(f'{name} {api_version} == {current_version}')
                    elif vc == 1:
                        print(f'{name} {api_version} > {current_version}')
                        scripts_to_update.append((iguid, values))
                if unmatched_names:
                    details = ', '.join([
                        (f'{n} (replaced by {RENAMED_COMPONENTS[n]})'
                         if n in RENAMED_COMPONENTS else
                         f'{n} ({REMOVED_COMPONENTS[n]})'
                         if n in REMOVED_COMPONENTS else n)
                        for n in sorted(unmatched_names)
                    ])
                    msg = (
                        f'{len(unmatched_names)} {CATEGORY} components in '
                        'this document have no source on the server and '
                        f'cannot be updated in place: {details}. Replace '
                        'them with the current components from the toolbar.'
                    )
                    self._addWarning(msg)
                    Status.Add(msg)
                if not scripts_to_update:
                    msg = 'No scripts in document need updating!'
                    self._addRemark(msg)
                    Status.Add(msg)
                else:
                    msg = (
                        f'Found {len(scripts_to_update)} script '
                        'components that need updating.'
                    )
                    self._addRemark(msg)
                    Status.Add(msg)

                # check for installed userobjects
                uo_dir = self.get_userobjects_dir()
                uo_mask = os.path.join(uo_dir, '**', 'DDU_CSC_*.ghuser')
                installed_uos = [os.path.normpath(p) for p in glob.glob(
                    os.path.normpath(uo_mask),
                    recursive=True
                )]
                if installed_uos:
                    uo_install_dir = os.path.dirname(installed_uos[0])
                else:
                    uo_install_dir = os.path.join(uo_dir, CATEGORY)
                installed_uo_paths = {
                    os.path.splitext(os.path.basename(p))[0]: p
                    for p in installed_uos
                }
                installed_uo_names = list(installed_uo_paths.keys())
                msg = f'Found {len(installed_uos)} installed UserObjects.'
                self._addRemark(msg)
                Status.Add(msg)

                # check for userobjects on server
                api_uo_names = self.get_api_userobject_names(auth_core)
                if api_uo_names is None:
                    msg = 'Failed to get userobject names from server.'
                    self._addError(msg)
                    Status.Add(msg)
                    return Status
                msg = f'Found {len(api_uo_names)} UserObjects on server.'
                self._addRemark(msg)
                Status.Add(msg)

                # identify missing userobjects on disk
                set_installed_uo_names = set(installed_uo_names)
                missing_uo_names = [
                    uo for uo in api_uo_names
                    if uo not in set_installed_uo_names
                ]
                stale_uo_names = [
                    uo for uo in set_installed_uo_names
                    if uo not in api_uo_names
                ]
                if missing_uo_names:
                    msg = (
                        f'Found {len(missing_uo_names)} UserObjects that '
                        'are not installed! Run InstallUpdates to install'
                        'them.'
                    )
                    self._addRemark(msg)
                    Status.Add(msg)
                if stale_uo_names:
                    msg = (
                        f'Found {len(stale_uo_names)} stale UserObjects not '
                        'on server (will be deleted on InstallUpdates): '
                        f'{", ".join(sorted(stale_uo_names))}'
                    )
                    self._addWarning(msg)
                    Status.Add(msg)
                library = self.check_library(auth_core)
                Status.Add(library['text'])
                if (scripts_to_update or missing_uo_names or stale_uo_names
                        or library['install']):
                    self._state('Updates available')
                else:
                    self._state('Up to date')
            if InstallUpdates:
                if not CheckForUpdates:
                    msg = 'CheckForUpdates must be True to install updates!'
                    self._addWarning(msg)
                    Status.Add(msg)
                    return Status

                # loop over scripts that need updates
                replaced = []
                if len(scripts_to_update) > 0:
                    for iguid, values in scripts_to_update:
                        (script_type,
                         nickname,
                         name,
                         obj,
                         current_source) = values
                        full_name = CATEGORY + '_' + name
                        new_source = self.get_api_source_file_text(
                            auth_core,
                            full_name
                        )
                        if new_source is None:
                            msg = (
                                f'Failed to get source file {full_name} '
                                'from server.'
                            )
                            self._addError(msg)
                            Status.Add(msg)
                            return Status
                        res = self.replace_scriptcomp_source(
                            values,
                            new_source
                        )
                        if not res:
                            msg = (
                                f'Failed to replace source for {nickname} '
                                'with new version! Please contact support '
                                '(lol)'
                            )
                            self._addError(msg)
                            Status.Add(msg)
                            return Status
                        replaced.append(obj)
                        msg = (
                            f'Replaced source for {nickname} with new version!'
                        )
                        self._addRemark(msg)
                        Status.Add(msg)
                    self.expire_replaced(replaced)

                # currently, we need to install/replace all userobjects
                # since we can't check userobjects file versions
                # TODO: add userobject file version checking
                # first, we delete all stale user objects, using the actual
                # path each userobject was discovered at (they may live in
                # different subfolders due to the recursive glob)
                deleted_stale = 0
                for uo_name in stale_uo_names:
                    stale_file = (
                        installed_uo_paths.get(uo_name) or
                        os.path.join(uo_install_dir, uo_name + '.ghuser')
                    )
                    try:
                        os.remove(stale_file)
                        deleted_stale += 1
                    except OSError as e:
                        msg = (
                            f'Could not delete stale UserObject {uo_name}: '
                            f'{str(e)}'
                        )
                        self._addWarning(msg)
                        Status.Add(msg)
                if stale_uo_names:
                    msg = (
                        f'Deleted {deleted_stale} of {len(stale_uo_names)} '
                        'stale UserObject files.'
                    )
                    self._addRemark(msg)
                    Status.Add(msg)
                missing_uo_names = api_uo_names
                # loop over missing userobjects and save them
                written_uo_files = []
                for uo_name in missing_uo_names:
                    # get new userobject bytes from api server
                    new_uo_bytes = self.get_api_userobject_bytes(
                        auth_core,
                        uo_name
                    )
                    if new_uo_bytes is None:
                        msg = (
                            f'Failed to get userobject {uo_name} from server.'
                        )
                        self._addError(msg)
                        Status.Add(msg)
                        return Status
                    os.makedirs(uo_install_dir, exist_ok=True)
                    out_file = Path(
                        os.path.join(uo_install_dir, uo_name + '.ghuser')
                    )
                    with open(out_file, 'wb') as f:
                        f.write(new_uo_bytes)
                    written_uo_files.append(str(out_file.resolve()))
                msg = f'Installed {len(written_uo_files)} UserObject files!'
                self._addRemark(msg)
                Status.Add(msg)
                restart = False
                if library['install']:
                    restart = self.install_library_now(library, Status)
                msg = 'All updates installed successfully!'
                self._addRemark(msg)
                Status.Add(msg)
                self._state('Restart Rhino' if restart else 'Updated')

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(e)}')

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(e)}')

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            self._addError(msg)

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)

        # return status message
        return Status
