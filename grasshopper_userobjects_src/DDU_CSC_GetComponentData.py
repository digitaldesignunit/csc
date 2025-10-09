#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'GetComponentData'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'GetComponentData'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Extracts component data from geometry userdata with '
    'error handling'
)


class CSC_GetComponentData(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251009
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def extract_component_data_from_geometry(self, geometry):
        """
        Extract component data from geometry userdata.

        Args:
            geometry: Rhino geometry object with userdata

        Returns:
            Component data dictionary or None
        """
        try:
            if hasattr(geometry, 'GetUserString'):
                userdata = geometry.GetUserString('csc_component')
                if userdata:
                    return json.loads(userdata)
                else:
                    self._addWarning('No csc_component userdata found')
            else:
                self._addWarning('Geometry object does not support userdata')
        except json.JSONDecodeError as e:
            self._addError(f'Invalid JSON in userdata: {str(e)}')
        except Exception as e:
            self._addError(f'Error extracting component data: {str(e)}')
        return None

    def RunScript(self,
            Geometry: System.Collections.Generic.List[Rhino.Geometry.GeometryBase]):
        """
        Main execution method for extracting component data from geometry.

        Args:
            Geometry: Geometry objects with component userdata

        Returns:
            Component data as JSON strings
        """
        # Initialize param descriptions
        self.InputParams[0].Description = (
            'Geometry objects with component userdata'
        )

        # Initialize output param descriptions
        self.OutputParams[0].Description = (
            'Component data as JSON strings extracted from '
            'geometry userdata'
        )

        # Set up output tree
        ComponentData = Grasshopper.DataTree[System.Object]()

        # Validate input
        if not Geometry:
            msg = 'Input geometry failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return ComponentData

        try:
            self.Component.Message = 'Extracting component data...'

            # Handle single geometry or list of geometries
            successful_extractions = 0

            for i, geo in enumerate(Geometry):
                if geo is None:
                    self._addWarning(f'Geometry at index {i} is None, '
                                     f'skipping')
                    continue

                # Extract component data
                component_data = self.extract_component_data_from_geometry(
                    geo)
                if component_data:
                    # Add to output
                    ComponentData.Add(
                        json.dumps(component_data),
                        Grasshopper.Kernel.Data.GH_Path(i)
                    )
                    successful_extractions += 1
                    self._addRemark(f'Successfully extracted component data '
                                    f'from geometry {i}')
                else:
                    # Add empty string to maintain data tree structure
                    ComponentData.Add(
                        '',
                        Grasshopper.Kernel.Data.GH_Path(i)
                    )
                    self._addWarning(f'Failed to extract component data '
                                     f'from geometry {i}')

            # Update success message
            if successful_extractions == 0:
                msg = 'No component data found in any geometry objects'
                self._addError(msg)
                self.Component.Message = msg
            elif successful_extractions == len(Geometry):
                self.Component.Message = (
                    f'Successfully extracted component data from '
                    f'{successful_extractions} geometry objects'
                )
                self._addRemark(f'Extracted component data from '
                                f'{successful_extractions} out of '
                                f'{len(Geometry)} geometry objects')
            else:
                self.Component.Message = (
                    f'Extracted component data from '
                    f'{successful_extractions} out of '
                    f'{len(Geometry)} geometry objects'
                )
                self._addWarning('Some geometry objects did not contain '
                                 'valid component data')

            return ComponentData

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
            return ComponentData
