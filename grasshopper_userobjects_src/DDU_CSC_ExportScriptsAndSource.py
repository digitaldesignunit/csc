# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA
import GhPython as ghpy  # type: ignore[reportMissingImport] # NOQA
import ScriptComponents as scomp  # type: ignore[reportMissingImport] # NOQA
import RhinoCodePluginGH as rcpgh  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = "ExportScriptsAndSource"  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = "ExportScriptsAndSource"  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = "DDU_CSC"  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = "0 Development"  # type: ignore[reportUnedfinedVariable] # NOQA


class ExportScriptsAndSource(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach (based on a Python Script by Anders Holden Deleuran)  # NOQA
    License: MIT License
    Version: 251009
    """

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
        import re

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
        import re

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

        return script_components

    def process_script_components(
            self,
            script_components: dict,
            set_category: str):
        """
        Process found script components and get unique components.
        """
        unique_script_components = {}

        OldScriptsDebug = []
        CategoryDebug = []
        VersionDebug = []
        InfoMessages = []

        for iguid, values in script_components.items():
            script_type, nickname, name, obj, source = values
            category = obj.Category
            version = self.get_source_version(source)
            script_id = nickname + ' ' + name
            # NOT SEEN YET SCRIPT COMPONENTS
            if script_id not in unique_script_components:
                version_present = True
                category_match = True
                if script_type == 'GHPY':
                    OldScriptsDebug.append(
                        f'{script_type} - {nickname} ({name})')
                    OldScriptsDebug.append(
                        '    - IS AN OLD GHPYTHON SCRIPT!')
                elif script_type == 'CS':
                    OldScriptsDebug.append(
                        f'{script_type} - {nickname} ({name})')
                    OldScriptsDebug.append('    - IS AN OLD C# SCRIPT!')
                if category != set_category:
                    # create debug info messages
                    category_match = False
                    if category == 'Maths':
                        CategoryDebug.append(
                            f'{script_type} - {nickname} ({name})')
                        CategoryDebug.append(
                            f'    - HAS NO CATEGORY ({category}) (No Export)!')
                    else:
                        CategoryDebug.append(
                            f'{script_type} - {nickname} ({name})')
                        CategoryDebug.append(
                            f'    - {category} OUT OF SET CATEGORY '
                            f'{set_category} (No Export)!')
                if version is None:
                    version_present = False
                    # create debug info messages
                    VersionDebug.append(
                        ' '.join([script_type, nickname, name]))
                    VersionDebug.append('    - HAS NO VERSION! (No Export)')
                if category_match and version_present:
                    InfoMessages.append(f'{script_type} - {nickname} ({name})')
                    unique_script_components[script_id] = values
            # ALREADY SEEN SCRIPT COMPONENTS
            else:
                existing_source = unique_script_components[script_id][4]
                existing_version = self.get_source_version(existing_source)
                if version is None:
                    VersionDebug.append(f'{script_type} - {nickname} ({name})')
                    VersionDebug.append('    - HAS NO VERSION!')
                elif existing_version is None and version is not None:
                    VersionDebug.append(f'{script_type} - {nickname} ({name})')
                    VersionDebug.append(
                        f'    - VERSION {version} > ALREADY FOUND VERSION '
                        f'{existing_version}!')
                    # REPLACE FOUND "NONE" VERSION WITH NAMED VERSION!
                    raise
                elif self._compare_versions(version, existing_version) < 0:
                    VersionDebug.append(f'{script_type} - {nickname} ({name})')
                    VersionDebug.append(
                        f'    - VERSION {version} < {existing_version}! '
                        'Continuing...')
                    # REPLACE THE SOURCE OF THE LOWER VERSION
                    # WITH HIGHER VERSION SOURCE!
                    continue
                elif self._compare_versions(version, existing_version) > 0:
                    VersionDebug.append(f'{script_type} - {nickname} ({name})')
                    VersionDebug.append(
                        f'    - VERSION {version} > ALREADY FOUND VERSION '
                        f'{existing_version}!')
                    # REPLACE THE OBJECT IN DICT WITH NEWER VERSION
                    raise
        return (unique_script_components, OldScriptsDebug, CategoryDebug,
                VersionDebug, InfoMessages)

    def export_scriptcomp_usrobj(self, scriptcomp, usrobjpath, iconpath=''):
        """
        Automates the creation of a GHPython user object. Based on this thread:
        http://www.grasshopper3d.com/forum/topics/change-the-default-values-for-userobject-popup-menu
        scriptcomp = [script_type, nickname, name, obj, source]
        """
        try:
            # Make a user object
            uo = Grasshopper.Kernel.GH_UserObject()
            # Get component object
            obj = scriptcomp[3]
            # Process icon
            if iconpath:
                obj.SetIconOverride(System.Drawing.Bitmap.FromFile(iconpath))
            uo.Icon = obj.Icon_24x24
            # Set its properties based on the GHPython component properties
            uo.BaseGuid = obj.ComponentGuid
            uo.Exposure = ghenv.Component.Exposure.primary  # type: ignore[reportUnedfinedVariable] # NOQA
            uo.Description.Name = obj.Name
            uo.Description.Description = obj.Description
            uo.Description.Category = obj.Category
            uo.Description.SubCategory = obj.SubCategory
            # Set the user object data and save to file
            uo.SetDataFromObject(obj)
            uo.Path = os.path.join(
                usrobjpath, obj.Category + '_' + obj.Name + '.ghuser')
            uo.SaveToFile()
        except Exception as e:
            print(e)
            return False
        return True

    def export_scriptcomp_source(self, scriptcomp, srcpath):
        """
        Export the source code of a script component
        scriptcomp = [script_type, nickname, name, obj, source]
        """
        # Get code and lines of code
        script_type = scriptcomp[0]
        name = scriptcomp[2]
        obj = scriptcomp[3]
        source = scriptcomp[4]
        code = source.replace('\r', '')
        lines = code.splitlines()
        loc = len(lines)
        # Check/make source file folder
        srcpath = os.path.join(srcpath)
        if not os.path.isdir(srcpath):
            os.makedirs(srcpath)
        # Write code to file
        if script_type == 'PY3' or script_type == 'IPY2':
            ext = '.py'
        elif script_type == 'CS9':
            ext = '.cs'
        else:
            # DO NOT EXPORT OLD SCRIPTS!
            ext = None
        if ext:
            src_file = os.path.join(srcpath, obj.Category + '_' + name + ext)
            with open(src_file, 'w') as f:
                f.write(code)
        return loc

    def RunScript(self,
            RunComponentAnalysis: bool,
            ExportUserObjectsAndSource: bool,
            Category: str,
            UserObjFolder,
            SourceFolder,
            IconPath: str):
        # Init outputs
        OldScriptsDebug = Grasshopper.DataTree[object]()
        CategoryDebug = Grasshopper.DataTree[object]()
        VersionDebug = Grasshopper.DataTree[object]()
        InfoMessages = Grasshopper.DataTree[object]()

        # Iterate the canvas and get to the GHPython components
        grasshopper_document = ghenv.Component.OnPingDocument()  # type: ignore[reportUnedfinedVariable] # NOQA
        gh_dir = os.path.dirname(grasshopper_document.FilePath)

        usrobjpath = os.path.normpath(
            os.path.abspath(os.path.join(gh_dir, UserObjFolder)))
        srcpath = os.path.normpath(
            os.path.abspath(os.path.join(gh_dir, SourceFolder)))
        iconpath = os.path.normpath(
            os.path.abspath(os.path.join(gh_dir, IconPath)))

        if RunComponentAnalysis:
            # loop over all objects on the grasshopper canvas
            # and identify the components to export scriptsource from
            script_components = self.process_document_objects(
                grasshopper_document, verbose=False)

            # - are all "same" scripts the same code?
            # - are there scripts without category or version attribute?
            # - separate old from new scripts, dont export old scripts!
            (unique_script_components,
             OldScriptsDebug,
             CategoryDebug,
             VersionDebug,
             InfoMessages) = self.process_script_components(
                script_components, Category)

        # HERE LOOP OVER UNIQUE COMPONENTS
        if ExportUserObjectsAndSource and RunComponentAnalysis:
            # - SAVE USEROBJECT
            # - SAVE SOURCE
            for script_id, scriptcomp in unique_script_components.items():
                loc = self.export_scriptcomp_source(scriptcomp, srcpath)
                res = self.export_scriptcomp_usrobj(
                    scriptcomp, usrobjpath, iconpath)
                print(res, loc)
        elif ExportUserObjectsAndSource and not RunComponentAnalysis:
            rml = ghenv.Component.RuntimeMessageLevel.Warning  # type: ignore[reportUnedfinedVariable] # NOQA
            ghenv.Component.AddRuntimeMessage(  # type: ignore[reportUnedfinedVariable] # NOQA
                rml,
                'UserObjects and Source cannot be exported without running '
                'Component Analysis!')

        return OldScriptsDebug, CategoryDebug, VersionDebug, InfoMessages
