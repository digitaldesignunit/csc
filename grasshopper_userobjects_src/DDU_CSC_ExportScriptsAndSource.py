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
import os
import re
from functools import cmp_to_key

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import GH_IO  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA
import GhPython as ghpy  # type: ignore[reportMissingImport] # NOQA
import ScriptComponents as scomp  # type: ignore[reportMissingImport] # NOQA
import RhinoCodePluginGH as rcpgh  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = "ExportScriptsAndSource"  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = "ExportScriptsAndSource"  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = "DDU_CSC"  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = "0 Development"  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Analyzes the current Grasshopper document to identify script components, '
    'extracts their source code, and can export them as Grasshopper User '
    'Objects (.ghuser) and raw source files (.py, .c'
)


class ExportScriptsAndSource(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach (based on a Python Script by Anders Holden Deleuran)  # NOQA
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
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'Run the analysis of all scriptable components within '
            'the document.\n'
            'Updates all recognized \'old\' script versions '
            'to the latest available script version within the doc.'
        )
        self.InputParams[1].Description = (
            'Export scripts as source files and UserObjects.\n'
            'NOTE: Only runs if RunComponentAnalysis is True!'
        )
        self.InputParams[2].Description = (
            'Target category for component export. Will only '
            'export components that have this category set.'
        )
        self.InputParams[3].Description = (
            'Folders to save UserObjects in.\n'
            'NOTE: Resolves environment variables and relative'
            'paths based on the GH document.'
        )
        self.InputParams[4].Description = (
            'Folders to save \'pasteable\' XML representations '
            'of UserObjects in.\n'
            'NOTE: Resolves environment variables and relative'
            'paths based on the GH document.'
        )
        self.InputParams[5].Description = (
            'Folder to save script source files in.\n'
            'NOTE: Resolves environment variables and relative'
            'paths based on the GH document.'
        )
        self.InputParams[6].Description = (
            '24x24 png icon to set to the script components '
            'and UserObjects.'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Debug messages concerning deprecated script components.'
        )
        self.OutputParams[1+i].Description = (
            'Debug messages concerning different categories.'
        )
        self.OutputParams[2+i].Description = (
            'Debug messages concerning script versions.'
        )
        self.OutputParams[3+i].Description = (
            'General info messages'
        )
        self.OutputParams[4+i].Description = (
            'Messages concering replaced script sources '
            '(updated components)'
        )

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

    def process_script_components(
            self,
            script_components: dict,
            set_category: str):
        """
        Process found script components and get unique components.
        """

        OldScriptsDebug = []
        CategoryDebug = []
        VersionDebug = []
        InfoMessages = []
        UpdateMessages = []

        versioned_script_components = {}
        unique_script_components = {}

        for iguid, values in script_components.items():
            # extract data from dict object
            script_type, nickname, name, obj, source = values
            category = obj.Category
            version = self.get_source_version(source)
            category_match = category == set_category
            version_present = version is not None
            # script id will be used as key for the unique dict
            script_id = nickname + '_' + name + '_' + script_type
            # NOT SEEN YET SCRIPT COMPONENTS
            if script_id not in versioned_script_components:
                version_present = version is not None
                if script_type == 'GHPY':
                    OldScriptsDebug.append(
                        f'{script_type} - {nickname} ({name})')
                    OldScriptsDebug.append(
                        '    - IS AN OLD GHPYTHON SCRIPT!')
                elif script_type == 'CS':
                    OldScriptsDebug.append(
                        f'{script_type} - {nickname} ({name})')
                    OldScriptsDebug.append('    - IS AN OLD C# SCRIPT!')
                if not category_match:
                    # create debug info messages
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
                if not version_present:
                    # create debug info messages
                    VersionDebug.append(
                        ' '.join([script_type, nickname, name]))
                    VersionDebug.append('    - HAS NO VERSION! (No Export)')
                if category_match and version_present:
                    InfoMessages.append(f'{script_type} - {nickname} ({name})')
                    versioned_script_components[script_id] = [values]
            # ALREADY SEEN SCRIPT COMPONENTS
            else:
                existing_source = versioned_script_components[script_id][0][4]
                existing_version = self.get_source_version(existing_source)
                if version is None:
                    VersionDebug.append(f'{script_type} - {nickname} ({name})')
                    VersionDebug.append('    - HAS NO VERSION!')
                    # NO VERSION, CONTINUE!
                    continue
                elif existing_version is None and version is not None:
                    VersionDebug.append(f'{script_type} - {nickname} ({name})')
                    VersionDebug.append(
                        f'    - VERSION {version} > ALREADY FOUND VERSION '
                        f'{existing_version}!')
                    # REPLACE FOUND "NONE" VERSION WITH NAMED VERSION!
                    raise NotImplementedError(
                        'Correcting missing Version is not implemented yet!'
                    )
                elif self._compare_versions(version, existing_version) < 0:
                    VersionDebug.append(f'{script_type} - {nickname} ({name})')
                    VersionDebug.append(
                        f'    - VERSION {version} < {existing_version}! '
                        'Updating Source...')
                    versioned_script_components[script_id].append(values)
                elif self._compare_versions(version, existing_version) > 0:
                    VersionDebug.append(f'{script_type} - {nickname} ({name})')
                    VersionDebug.append(
                        f'    - VERSION {version} > ALREADY FOUND VERSION '
                        f'{existing_version}!')
                    versioned_script_components[script_id].append(values)
        # LOOP OVER VERSIONED COMPONENTS AND UPDATE OLD SOURCES
        # THEN UPDATE UNIQUE COMPONENT DICT
        for script_id, versioned_comps in versioned_script_components.items():
            # check if multiple versions were found
            if len(versioned_comps) == 1:
                # ONLY ONE VERSION -> ADD TO UNIQUE DICT
                unique_script_components[script_id] = versioned_comps[0]
            else:
                # MULTIPLE VERSIONS -> SORT, CHECK AND DECIDE
                versions = [self.get_source_version(vc[4])
                            for vc in versioned_comps]
                sorted_versions, sorted_comps = zip(*sorted(
                    zip(versions, versioned_comps),
                    key=cmp_to_key(
                        lambda x, y: self._compare_versions(x[0], y[0])
                    ),
                    reverse=True
                ))
                # convert to lists
                sorted_versions = list(sorted_versions)
                sorted_comps = list(sorted_comps)
                # pop latest script version
                latest_version = sorted_versions.pop(0)
                latest_comp = sorted_comps.pop(0)
                latest_source = latest_comp[4]
                # loop over remaining (older) versions and replace source
                for k, old_comp in enumerate(sorted_comps):
                    # REPLACE THE SOURCE OF THE LOWER VERSIONS
                    # WITH LATEST VERSIONS SOURCE!
                    repres = self._replace_scriptcomp_source(
                        old_comp,
                        latest_source,
                    )
                    if repres:
                        UpdateMessages.append(
                            f'Updated source for {latest_comp[1]}: '
                            f'{sorted_versions[k]} -> {latest_version}'
                        )
                # THEN UPDATE DICT!
                UpdateMessages.append(
                    f'Updated in Dict: {latest_comp[0]} - '
                    f'{latest_comp[1]} ({sorted_versions[k]} '
                    f'-> {latest_version})'
                )
                unique_script_components[script_id] = latest_comp
        # return unique result dict and message arrays
        return (unique_script_components, OldScriptsDebug, CategoryDebug,
                VersionDebug, InfoMessages, UpdateMessages)

    def make_userobject(self, obj, iconpath=''):
        """
        Creates a UserObject from a GH document object
        """
        # Make a user object
        uo = Grasshopper.Kernel.GH_UserObject()
        # Process icon
        if iconpath:
            obj.SetIconOverride(System.Drawing.Bitmap.FromFile(iconpath))
        uo.Icon = obj.Icon_24x24
        # Set its properties based on the GHPython component properties
        uo.BaseGuid = obj.ComponentGuid
        uo.Exposure = obj.Exposure.primary
        uo.Description.Name = obj.Name
        uo.Description.NickName = obj.NickName
        uo.Description.Description = obj.Description
        uo.Description.Category = obj.Category
        uo.Description.SubCategory = obj.SubCategory
        # Set the user object data and save to file
        uo.SetDataFromObject(obj)
        return uo

    def export_scriptcomp_usrobj(self, scriptcomp, usrobjpath, iconpath=''):
        """
        Automates the creation of a GHPython user object. Based on this thread:
        http://www.grasshopper3d.com/forum/topics/change-the-default-values-for-userobject-popup-menu
        scriptcomp = [script_type, nickname, name, obj, source]
        """
        try:
            # Make a user object
            obj = scriptcomp[3]
            uo = self.make_userobject(obj, iconpath)
            uo.Path = os.path.join(
                usrobjpath, obj.Category + '_' + obj.Name + '.ghuser')
            # Ensure the directory exists before saving
            os.makedirs(usrobjpath, exist_ok=True)
            uo.SaveToFile()
        except Exception as e:
            print(e)
            return False
        return True

    def export_scriptcomp_xml(self, scriptcomp, xmlpath, iconpath=''):
        """
        Export scriptable component as 'pasteable' XML
        """
        try:
            obj = scriptcomp[3]
            uo = self.make_userobject(obj, iconpath)
            # instantiate userobject to finally get a copy of the
            # DocumentObject and set new instanceguid (precaution)
            uo_comp = uo.InstantiateObject()
            uo_comp.NewInstanceGuid()
            # overwrite object location on canvas
            uo_comp.Attributes.Pivot = System.Drawing.PointF(20, 20)
            # create new doc and add object
            new_doc = Grasshopper.Kernel.GH_Document()
            new_doc.AddObject(uo_comp, False, 0)
            # create archive that can be serialized
            archive = GH_IO.Serialization.GH_Archive()
            archive.AppendObject(new_doc, 'Clipboard')
            # last but not least: serialize to XML - hooray!
            xml = archive.Serialize_Xml()
            xml = xml.replace('\r', '')
            if not os.path.isdir(xmlpath):
                os.makedirs(xmlpath)
            xmlfile = os.path.join(
                xmlpath, obj.Category + '_' + obj.Name + '.xml'
            )
            with open(xmlfile, 'w') as f:
                f.write(xml)
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
        try:
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
        except Exception as e:
            print(e)
            return False, None
        return True, loc

    def RunScript(self,
            RunComponentAnalysis: bool,
            ExportUserObjectsAndSource: bool,
            Category: str,
            UserObjFolders: System.Collections.Generic.List[str],
            XMLFolders: System.Collections.Generic.List[str],
            SourceFolders: System.Collections.Generic.List[str],
            IconPath: str):
        # Init outputs
        OldScriptsDebug = Grasshopper.DataTree[str]()
        CategoryDebug = Grasshopper.DataTree[str]()
        VersionDebug = Grasshopper.DataTree[str]()
        InfoMessages = Grasshopper.DataTree[str]()
        UpdateMessages = Grasshopper.DataTree[str]()

        # Iterate the canvas and get to the GHPython components
        grasshopper_document = ghenv.Component.OnPingDocument()  # type: ignore[reportUnedfinedVariable] # NOQA
        gh_dir = os.path.dirname(grasshopper_document.FilePath)

        usrobjpaths = [
            os.path.normpath(os.path.abspath(
                os.path.join(gh_dir, self._expand_path(uof))))
            for uof in UserObjFolders]
        xmlpaths = [os.path.normpath(
            os.path.abspath(os.path.join(
                gh_dir, self._expand_path(xmlf))))
            for xmlf in XMLFolders]
        srcpaths = [os.path.normpath(
            os.path.abspath(os.path.join(
                gh_dir, self._expand_path(srcf))))
            for srcf in SourceFolders]
        iconpath = os.path.normpath(
            os.path.abspath(os.path.join(
                gh_dir, self._expand_path(IconPath))))

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
             InfoMessages,
             UpdateMessages) = self.process_script_components(
                script_components, Category)

        # HERE LOOP OVER UNIQUE COMPONENTS
        if ExportUserObjectsAndSource and RunComponentAnalysis:
            for script_id, scriptcomp in unique_script_components.items():
                unionres = True
                # SAVE SOURCE IN ALL PATHS
                for src_path in srcpaths:
                    res, loc = self.export_scriptcomp_source(
                        scriptcomp, src_path
                    )
                    if not res:
                        unionres = False
                        break
                # SAVE XML FILES
                for xml_path in xmlpaths:
                    res = self.export_scriptcomp_xml(
                        scriptcomp, xml_path, iconpath
                    )
                    if not res:
                        unionres = False
                        break
                # SAVE USEROBJECT IN ALL PATHS
                for uo_path in usrobjpaths:
                    res = self.export_scriptcomp_usrobj(
                        scriptcomp, uo_path, iconpath
                    )
                    if not res:
                        unionres = False
                        break
                if unionres:
                    print(f'Exported: {scriptcomp[1]} - {loc} Lines of Code')
                else:
                    raise RuntimeError(f'Export failed for {scriptcomp[1]}!')
        elif ExportUserObjectsAndSource and not RunComponentAnalysis:
            rml = ghenv.Component.RuntimeMessageLevel.Warning  # type: ignore[reportUnedfinedVariable] # NOQA
            ghenv.Component.AddRuntimeMessage(  # type: ignore[reportUnedfinedVariable] # NOQA
                rml,
                'UserObjects and Source cannot be exported without running '
                'Component Analysis!')

        return (OldScriptsDebug, CategoryDebug,
                VersionDebug, InfoMessages, UpdateMessages)

