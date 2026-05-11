#! python3
# -*- coding: utf-8 -*-
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
import os  # NOQA
from datetime import datetime  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreatePublicDevelopmentFile'  # NOQA
ghenv.Component.NickName = 'CreatePublicDevelopmentFile'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '0 Development'  # NOQA
ghenv.Component.Description = (  # NOQA
    """
    This component can be used to create a sanitized Grasshopper development file
    in a specified folder.

    It creates a copy of the current Grasshopper document in
    memory, removes all components that belong to a specified group (i.e.
    developmclears specified panels containing sensitive information,
    and saves the modified document to a specified folder.

    The folder path can be relative, i.e. "..\\grasshopper_release".

    The filename can be specified, otherwise a timestamp-based filename will be
    generated.
    """
)


class CSC_CreatePublicDevelopmentFile(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260511
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
        """Performs some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'Run the document copy, object removal, and save operation'
        )
        self.InputParams[1].Description = (
            'List of names of optional GH_Panel objects to clear,'
            ' (i.e. for passwords)'
        )
        self.InputParams[2].Description = (
            'Folder path where to save the modified development document'
        )
        self.InputParams[3].Description = (
            'Optional filename for the saved document '
            '(without .gh extension)'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Success status of the operation (True/False)'
        )
        self.OutputParams[1+i].Description = (
            'Full path of the saved document'
        )
        self.OutputParams[2+i].Description = (
            'Status message describing the operation result'
        )

    def copy_document(self, source_doc):
        """
        Create a copy of the Grasshopper document in memory.

        Args:
            source_doc: The source Grasshopper document to copy

        Returns:
            GH_Document: A copy of the source document, or None if failed
        """
        try:
            if source_doc is None:
                self._addError('Source document is None')
                return None

            # Use the DuplicateDocument method to create a copy
            duplicate_doc = Grasshopper.Kernel.GH_Document.DuplicateDocument(
                source_doc
            )

            if duplicate_doc is None:
                self._addError('Failed to duplicate the document')
                return None

            self._addRemark('Successfully created document copy')
            return duplicate_doc

        except Exception as e:
            self._addError(f'Error copying document: {str(e)}')
            return None

    def clear_panels(self, doc, target_panels):
        """
        Clear all GH_Panel instances in the document with one of the specified
        names.
        """
        panels_cleared = 0
        try:
            # loop over target panels and clear them
            for panel in target_panels:
                # UserText property holds the panel contents so we clear it
                panel.UserText = ''
                # we clear the volatile data as well
                panel.ClearData()
                panels_cleared += 1
        except Exception as e:
            self._addError(f'Error clearing panels: {str(e)}')
            return panels_cleared
        # return target groups and objects
        return panels_cleared

    def find_panels_to_clear(self, doc, panel_names=[]):
        """
        Find all panels in the document with the specified name.
        """
        # get type for panels as string for verification
        paneltype = Grasshopper.Kernel.Special.GH_Panel
        paneltype_str = str(paneltype).split("'")[1]
        # loop over all document objects
        doc_objects = doc.Objects
        target_panels = []
        try:
            for doc_obj in doc_objects:
                # ensure matching panel name
                if panel_names and doc_obj.NickName in panel_names:
                    # ensure matching type
                    if str(doc_obj.GetType()) == paneltype_str:
                        target_panels.append(doc_obj)
        except Exception as e:
            self._addError(f'Error finding panels: {str(e)}')
            return None
        # return target panels
        return target_panels

    def save_document(self, doc, save_path, filename=None):
        """
        Save the Grasshopper document to the specified path.

        Args:
            doc: The Grasshopper document to save
            save_path: The folder path where to save the document
            filename: Optional filename
                      (if None, generates timestamp-basedname)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if doc is None:
                self._addError('Document is None, cannot save')
                return False, ''

            if not save_path:
                self._addError('Save path is empty')
                return False, ''

            # Handle relative paths - get the current GH
            # document directory as base
            current_doc = self.Component.OnPingDocument()
            if current_doc and current_doc.FilePath:
                current_dir = os.path.dirname(current_doc.FilePath)
                # Convert relative path to absolute path
                if not os.path.isabs(save_path):
                    save_path = os.path.normpath(
                        os.path.join(current_dir, save_path)
                    )
            else:
                # If no current document, use current working directory
                save_path = os.path.abspath(os.path.normpath(save_path))

            # Ensure the save directory exists
            if not os.path.exists(save_path):
                try:
                    os.makedirs(save_path, exist_ok=True)
                    self._addRemark(f'Created directory: {save_path}')
                except Exception as e:
                    self._addError(
                        f'Failed to create directory {save_path}: '
                        f'{str(e)}'
                    )
                    return False, ''

            # Generate filename if not provided
            if not filename:
                timestamp = datetime.now().strftime('%y%m%d_%H%M%S')
                filename = f'{timestamp}_ReleaseFile.gh'

            # Ensure filename has .gh extension
            if not filename.endswith('.gh'):
                filename += '.gh'

            # Create full file path
            full_path = os.path.join(save_path, filename)

            # Use GH_DocumentIO to save the document
            # (following SaveAndSaveGHX pattern)
            doc_io = Grasshopper.Kernel.GH_DocumentIO(doc)

            # Save the document
            success = doc_io.SaveQuiet(full_path)

            if success:
                self._addRemark(f'Document saved successfully: {full_path}')
                return True, full_path
            else:
                self._addError(f'Failed to save document to: {full_path}')
                return False, ''
        except Exception as e:
            self._addError(f'Error saving document: {str(e)}')
            return False, ''

    def validate_inputs(self, clear_panel_names, save_path):
        """
        Validate the input parameters.

        Args:
            save_path: The path where to save the document

        Returns:
            bool: True if inputs are valid, False otherwise
        """
        if not save_path or not save_path.strip():
            self._addError('Save path cannot be empty')
            return False

        if not clear_panel_names:
            clear_panel_names = []
        for cpn in clear_panel_names:
            if not isinstance(cpn, str):
                self._addError('ClearPanelNames contains non-string')
                return False

        # Check if save path is valid
        try:
            # Handle relative paths - get the current
            # GH document directory as base
            current_doc = self.Component.OnPingDocument()
            if current_doc and current_doc.FilePath:
                current_dir = os.path.dirname(current_doc.FilePath)
                # Convert relative path to absolute path
                if not os.path.isabs(save_path):
                    normalized_path = os.path.normpath(
                        os.path.join(current_dir, save_path)
                    )
                else:
                    normalized_path = os.path.normpath(save_path)
            else:
                # If no current document, use current working directory
                normalized_path = os.path.abspath(os.path.normpath(save_path))
            # Check if the parent directory exists or can be created
            parent_dir = os.path.dirname(normalized_path)
            if parent_dir and not os.path.exists(parent_dir):
                # Try to create the parent directory
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except Exception:
                    self._addError(f'Cannot create directory: {parent_dir}')
                    return False
        except Exception as e:
            self._addError(f'Invalid save path: {str(e)}')
            return False

        return True

    def RunScript(self,
            Run: bool,
            ClearPanelNames: System.Collections.Generic.List[str],
            DevelopmentPath: str,
            Filename: str):

        # Initialize output variables
        success = False
        components_removed = 0
        saved_file_path = ''
        status_message = ''

        # Check if execution is requested
        if not Run:
            status_message = 'Run is False - operation not performed'
            self.Component.Message = status_message
            return (success, saved_file_path,
                    status_message)

        # Validate inputs
        if not self.validate_inputs(
                ClearPanelNames, DevelopmentPath):
            status_message = 'Input validation failed'
            self.Component.Message = status_message
            return (success, saved_file_path,
                    status_message)

        # Get the current Grasshopper document
        current_doc = self.Component.OnPingDocument()
        if current_doc is None:
            status_message = 'No active Grasshopper document found'
            self._addError(status_message)
            self.Component.Message = status_message
            return (success, saved_file_path,
                    status_message)

        # Step 1: Copy the current document
        self.Component.Message = 'Copying document...'
        copied_doc = self.copy_document(current_doc)
        if copied_doc is None:
            status_message = 'Failed to copy document'
            self.Component.Message = status_message
            return (success, saved_file_path,
                    status_message)

        # Step 2: Find the panels to clear
        self.Component.Message = 'Finding groups...'
        target_panels = self.find_panels_to_clear(
            copied_doc, ClearPanelNames
        )

        # Step 3: Clear Panels if ClearPanelNames were supplied
        if target_panels:
            self.Component.Message = 'Clearing Panels...'
            panels_cleared = self.clear_panels(copied_doc, target_panels)
            if panels_cleared == 0:
                status_message = ('No panels have been cleared!')
                self._addWarning(status_message)

        # Step 4: Save the modified document
        self.Component.Message = 'Saving document...'
        save_success, saved_file_path = self.save_document(
            copied_doc,
            DevelopmentPath,
            Filename
        )
        if save_success:
            saved_file_path = os.path.normpath(
                os.path.abspath(saved_file_path)
            )
            success = True
            status_message += f'\n Saved development file to: {saved_file_path}'
            self.Component.Message = 'Operation completed successfully'
        else:
            status_message += '\n Failed to save document!'
            self.Component.Message = 'Save operation failed'

        # set message
        self.Component.Message = 'Operation completed successfully'
        # return results
        return (success, saved_file_path, status_message)
