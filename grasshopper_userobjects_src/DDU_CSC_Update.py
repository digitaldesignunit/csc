# -*- coding: utf-8 -*-
#! python3
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests
# r: numpy
# r: scipy
# r: scikit-learn
# r: robust-laplacian
# r: potpourri3d

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import os
import re
import glob
from pathlib import Path

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA
import GhPython as ghpy  # type: ignore[reportMissingImport] # NOQA
import ScriptComponents as scomp  # type: ignore[reportMissingImport] # NOQA
import RhinoCodePluginGH as rcpgh  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'Update'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'CSC_Update'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '0 Development'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Updates component sources in doc an userobjects on disk'
)


class CSC_Update(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251030.1
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
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
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'The ComponentData that was fetched from the server as JSON. '
            'Use \'DisassembleComponent\' to access the individual fields '
            'ready for Grasshopper'
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

    def get_source_version(self, source):
        """
        Attempts to get the first instance of the word "version"
        (or, "Version") in a multi line string. Then attempts to extract a
        version string from this line where the word "version" exists.
        Supports formats like:
            Version: 160121
            Version: 251009.1
            Version: 251009a
        """
        # Get first line with version in it
        src_lower = source.lower()
        version_str = [ln for ln in src_lower.split('\n') if "version" in ln]
        if version_str:
            # Extract version string using regex to handle complex formats
            # Look for patterns like: 251009, 251009.1, 251009a, etc.
            version_match = re.search(
                r'(\d+(?:\.\d+)?[a-zA-Z]?)', version_str[0])
            if version_match:
                version_text = version_match.group(1)
                return self._parse_version_string(version_text)
        return None

    def _parse_version_string(self, version_str):
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

    def _compare_versions(self, version1, version2):
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

    def _expand_path(self, path):
        """
        Expand environment variables in a path string.
        Handles %APPDATA%, %USERPROFILE%, %TEMP%, etc.
        """
        if not path:
            return path
        return os.path.expandvars(path)

    def _replace_scriptcomp_source(
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
            # script id will be used as key for the unique dict
            script_id = nickname + '_' + name + '_' + script_type
            if category_match and version_present:
                versioned_script_components.append((iguid, values))
        return versioned_script_components

    def _get_userobjects_dir(self):
        """Get platform-specific UserObjects directory."""
        dir = Grasshopper.Folders.DefaultUserObjectFolder
        return dir

    def RunScript(self, CheckForUpdates, InstallUpdates):
        CATEGORY = 'DDU_CSC'
        Status = Grasshopper.DataTree[System.Object]()
        self.Component.Message = None
        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return Status

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            Status.Add(msg)
            return Status

        try:
            if CheckForUpdates:
                msg = (f'Searching current document for {CATEGORY} script components...')
                self.Component.Message = msg
                # loop through the document to find all script components
                doc = self.Component.OnPingDocument()
                script_components = self.process_script_components(
                    self.process_document_objects(doc),
                    CATEGORY
                )
                msg = f'Found {len(script_components)} {CATEGORY} script components in current document (including duplicates).'
                self._addRemark(msg)
                Status.Add(msg)
                # make request to fetch all source file names and versions
                msg = (f'Checking Server for updates...')
                self.Component.Message = msg
                api_src_versions = {}
                response = auth_core.authorized_get('/ghupdates/src_names')
                if response.status_code == 200:
                    api_src_files_json = response.json()
                    for file_tuple in api_src_files_json:
                        name = file_tuple[0]
                        version = tuple(file_tuple[1])
                        api_src_versions[name] = version
                msg = f'Found {len(api_src_files_json)} unique script component source files on server.'
                self._addRemark(msg)
                Status.Add(msg)

                # loop over scripts in document
                scripts_to_update = []
                for iguid, values in script_components:
                    script_type, nickname, name, obj, current_source = values
                    current_version = self.get_source_version(current_source)
                    try:
                        full_name = CATEGORY + '_' + name
                        api_version = api_src_versions[full_name]
                        vc = self._compare_versions(api_version, current_version)
                        if vc == 0:
                            print(f'{name} {api_version} == {current_version}')
                        elif vc == 1:
                            print(f'{name} {api_version} > {current_version}')
                            scripts_to_update.append((iguid, values))
                    except KeyError:
                        print(f'{full_name} not found on server!')
                        continue
                if not scripts_to_update:
                    msg = f'No scripts in document need updating!'
                    self._addRemark(msg)
                    self.Component.Message = msg
                    Status.Add(msg)

                # check for installed userobjects
                uo_dir = self._get_userobjects_dir()
                uo_mask = os.path.join(uo_dir, '**', 'DDU_CSC_*.ghuser')
                installed_uos = [os.path.normpath(p) for p in glob.glob(
                    os.path.normpath(uo_mask),
                    recursive=True
                )]
                if installed_uos:
                    uo_install_dir = os.path.dirname(installed_uos[0])
                else:
                    uo_install_dir = os.path.join(uo_dir, CATEGORY)
                installed_uo_names = [os.path.splitext(os.path.basename(p))[0] for p in installed_uos]
                msg = f'Found {len(installed_uos)} installed UserObjects.'
                self._addRemark(msg)
                Status.Add(msg)

                # check for userobjects on server
                api_uo_names = []
                response = auth_core.authorized_get('/ghupdates/userobject_names')
                if response.status_code == 200:
                    api_uo_names = list(response.json())
                msg = f'Found {len(api_uo_names)} UserObjects on server.'
                self._addRemark(msg)
                Status.Add(msg)

                # identify missing userobjects on disk
                set_installed_uo_names = set(installed_uo_names)
                missing_uo_names = [uo for uo in api_uo_names if uo not in set_installed_uo_names]
                if missing_uo_names:
                    msg = f'Found {len(missing_uo_names)} UserObjects that are not installed! Run InstallUpdates to install them.'
                    self._addRemark(msg)
                    Status.Add(msg)

            if InstallUpdates:
                if not CheckForUpdates:
                    msg = f'CheckForUpdates must be True to install updates!'
                    self._addWarning(msg)
                    Status.Add(msg)
                    return Status
                
                # loop over scripts that need updates
                if len(scripts_to_update) > 0:
                    for iguid, values in scripts_to_update:
                        script_type, nickname, name, obj, current_source = values
                        full_name = CATEGORY + '_' + name
                        response = auth_core.authorized_get(f'/ghupdates/src/{full_name}')
                        if response.status_code == 200:
                            new_source = response.text
                            # HERE WE NEED TO REPLACE THE SOURCE!
                        else:
                            pass
                
                # loop over missing userobjects and save them
                written_uo_files = []
                for uo_name in missing_uo_names:
                    # get new userobject bytes from api server
                    response = auth_core.authorized_get(f'/ghupdates/userobject/{uo_name}')
                    response.raise_for_status()
                    os.makedirs(uo_install_dir, exist_ok=True)
                    out_file = Path(os.path.join(uo_install_dir, uo_name + '.ghuser'))
                    with open(out_file, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    written_uo_files.append(str(out_file.resolve()))
                msg = f'Installed {len(written_uo_files)} UserObject files!'
                self._addRemark(msg)
                Status.Add(msg)

            # elif response.status_code == 401:
            #     msg = 'Authentication failed. Please sign in again.'
            #     self._addError(msg)
            #     self.Component.Message = msg

            # elif response.status_code == 403:
            #     msg = 'Access denied. Insufficient permissions.'
            #     self._addError(msg)
            #     self.Component.Message = msg

            # elif response.status_code == 500:
            #     msg = 'Server error. Please try again later.'
            #     self._addWarning(msg)
            #     self.Component.Message = msg

            # else:
            #     msg = (f'Request failed with status code: '
            #            f'{response.status_code}')
            #     self._addError(msg)
            #     self.Component.Message = msg

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
