#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os  # NOQA
import re  # NOQA
import glob  # NOQA
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

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'Update'  # NOQA
ghenv.Component.NickName = 'CSC_Update'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '0 Development'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Updates component sources and userobjects in document from server.\n'
    'NOTE: CheckForUpdates must be True to check for updates AND to '
    'install updates! Switch on both to update everything.\n'
    'UPDATE_CHANNEL is a hardcoded GitHub branch name (default: main). '
    'It must match the remote branch exactly.'
)

# GitHub branch to pull sources and UserObjects from. Must match the remote
# branch name exactly (e.g. 'main', 'develop', 'feature/foo').
UPDATE_CHANNEL = 'v-0.5.0.0'

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
    'FetchGeometry': 'FetchReducedGeometry / FetchDetailedGeometry',
}


class CSC_Update(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260908.2
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

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

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def _channel_params(self):
        """Query params selecting the GitHub update channel (branch)."""
        return {'channel': UPDATE_CHANNEL}

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

    def get_api_source_versions(self, auth_core):
        """Get source versions from API."""
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
                f'Update channel "{UPDATE_CHANNEL}" was not found on GitHub. '
                'The branch name must match exactly.'
            )
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 401:
            msg = 'Authentication failed. Please sign in again.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 403:
            msg = 'Access denied. Insufficient permissions.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 500:
            msg = 'Server error. Please try again later.'
            self._addError(msg)
            self.Component.Message = msg
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
            self.Component.Message = msg
            return None
        return api_src_versions

    def get_api_userobject_names(self, auth_core):
        """Get userobject names from API."""
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
                f'Update channel "{UPDATE_CHANNEL}" was not found on GitHub. '
                'The branch name must match exactly.'
            )
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 401:
            msg = 'Authentication failed. Please sign in again.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 403:
            msg = 'Access denied. Insufficient permissions.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 500:
            msg = 'Server error. Please try again later.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        else:
            msg = (f'Request failed with status code: '
                   f'{response.status_code}')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return api_uo_names

    def get_api_source_file_text(self, auth_core, full_name):
        """Get source file from API."""
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
            self.Component.Message = msg
            return None
        elif response.status_code == 401:
            msg = 'Authentication failed. Please sign in again.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 403:
            msg = 'Access denied. Insufficient permissions.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 500:
            msg = 'Server error. Please try again later.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        else:
            msg = (f'Request failed with status code: '
                   f'{response.status_code}')
            self._addError(msg)
            self.Component.Message = msg
            return None

    def get_api_userobject_bytes(self, auth_core, uo_name):
        """Get userobject bytes from API."""
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
            self.Component.Message = msg
            return None
        elif response.status_code == 401:
            msg = 'Authentication failed. Please sign in again.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 403:
            msg = 'Access denied. Insufficient permissions.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        elif response.status_code == 500:
            msg = 'Server error. Please try again later.'
            self._addError(msg)
            self.Component.Message = msg
            return None
        else:
            msg = (f'Request failed with status code: '
                   f'{response.status_code}')
            self._addError(msg)
            self.Component.Message = msg
            return None

    def RunScript(self, CheckForUpdates, InstallUpdates):
        # hardcoded category of the components to update
        CATEGORY = 'DDU_CSC'
        # init output tree for status messages
        Status = Grasshopper.DataTree[System.Object]()
        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return Status
        if UPDATE_CHANNEL != 'main':
            channel_msg = (
                f'UPDATE_CHANNEL is "{UPDATE_CHANNEL}" (not main). '
                'Branch name must match the GitHub remote exactly.'
            )
            self._addWarning(channel_msg)
            Status.Add(channel_msg)
        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            Status.Add(msg)
            return Status
        msg = (
            'Toggle CheckForUpdates to True to check for updates on the '
            'server.'
        )
        self.Component.Message = msg
        try:
            if CheckForUpdates:
                msg = f'Using GitHub update channel: {UPDATE_CHANNEL}'
                self._addRemark(msg)
                Status.Add(msg)
                msg = (
                    f'Searching current document for {CATEGORY} script '
                    'components...'
                )
                self.Component.Message = msg
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
                    f'(channel: {UPDATE_CHANNEL})...'
                )
                self.Component.Message = msg
                api_src_versions = self.get_api_source_versions(auth_core)
                if api_src_versions is None:
                    msg = 'Failed to get source versions from server.'
                    self._addError(msg)
                    self.Component.Message = msg
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
                         if n in RENAMED_COMPONENTS else n)
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
                    self.Component.Message = msg
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
                    self.Component.Message = msg
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
                msg = (
                    'Toggle InstallUpdates to True to install updates from '
                    'server.'
                )
                self.Component.Message = msg
            if InstallUpdates:
                if not CheckForUpdates:
                    msg = 'CheckForUpdates must be True to install updates!'
                    self._addWarning(msg)
                    Status.Add(msg)
                    return Status

                # loop over scripts that need updates
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
                            self.Component.Message = msg
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
                            self.Component.Message = msg
                            Status.Add(msg)
                            return Status
                        msg = (
                            f'Replaced source for {nickname} with new version!'
                        )
                        self._addRemark(msg)
                        Status.Add(msg)
                        self.Component.Message = msg

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
                        self.Component.Message = msg
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
                msg = 'All updates installed successfully!'
                self._addRemark(msg)
                self.Component.Message = msg
                Status.Add(msg)

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        # return status message
        return Status
