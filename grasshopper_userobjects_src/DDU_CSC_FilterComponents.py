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

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FilterComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'FilterComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Filters a list of component data based on various criteria (type, '
    'material, dataset, complexity, fragment, bounding box dimensions). '
    'Works with local component data.'
)


class CSC_FilterComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251023
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def apply_filters(self, component_data: dict, filter_params: dict) -> bool:
        """
        Apply all filters to a single component and return True if it passes.
        """

        # Type filter
        if filter_params.get('type') and filter_params['type'].strip():
            if (component_data.get('type', '').lower() !=
                    filter_params['type'].lower()):
                return False

        # Material filter
        if filter_params.get('material') and filter_params['material'].strip():
            if (component_data.get('material', '').lower() !=
                    filter_params['material'].lower()):
                return False

        # Dataset filter
        if filter_params.get('dataset') and filter_params['dataset'].strip():
            if (component_data.get('dataset', '').lower() !=
                    filter_params['dataset'].lower()):
                return False

        # Complexity filter
        if filter_params.get('complexity') is not None:
            if component_data.get('complexity') != filter_params['complexity']:
                return False

        # Fragment filter
        if filter_params.get('fragment') is not None:
            if component_data.get('fragment') != filter_params['fragment']:
                return False

        # Bounding box filters
        bbx = component_data.get('bbx')
        if (bbx and isinstance(bbx, list) and len(bbx) >= 2):
            bbx_min = bbx[0]
            bbx_max = bbx[1]

            # X dimension filters
            if filter_params.get('min_x') is not None:
                if bbx_max[0] < filter_params['min_x']:
                    return False
            if filter_params.get('max_x') is not None:
                if bbx_min[0] > filter_params['max_x']:
                    return False

            # Y dimension filters
            if filter_params.get('min_y') is not None:
                if bbx_max[1] < filter_params['min_y']:
                    return False
            if filter_params.get('max_y') is not None:
                if bbx_min[1] > filter_params['max_y']:
                    return False

            # Z dimension filters
            if filter_params.get('min_z') is not None:
                if bbx_max[2] < filter_params['min_z']:
                    return False
            if filter_params.get('max_z') is not None:
                if bbx_min[2] > filter_params['max_z']:
                    return False

        return True

    def generate_filter_description(self, filter_params: dict) -> str:
        """Generates a human-readable description of the applied filters."""
        description = []
        if filter_params.get('type'):
            description.append(f'\nType: {filter_params["type"]}')
        if filter_params.get('material'):
            description.append(f'\nMaterial: {filter_params["material"]}')
        if filter_params.get('dataset'):
            description.append(f'\nDataset: {filter_params["dataset"]}')
        if filter_params.get('complexity') is not None:
            description.append(f'\nComplexity: {filter_params["complexity"]}')
        if filter_params.get('fragment') is not None:
            description.append(f'\nFragment: {filter_params["fragment"]}')

        # Handle bounding box filters with detailed information
        bbx_filters = []
        if filter_params.get('min_x') is not None:
            bbx_filters.append(f'\nX >= {filter_params["min_x"]:.2f}')
        if filter_params.get('max_x') is not None:
            bbx_filters.append(f'\nX <= {filter_params["max_x"]:.2f}')
        if filter_params.get('min_y') is not None:
            bbx_filters.append(f'\nY >= {filter_params["min_y"]:.2f}')
        if filter_params.get('max_y') is not None:
            bbx_filters.append(f'\nY <= {filter_params["max_y"]:.2f}')
        if filter_params.get('min_z') is not None:
            bbx_filters.append(f'\nZ >= {filter_params["min_z"]:.2f}')
        if filter_params.get('max_z') is not None:
            bbx_filters.append(f'\nZ <= {filter_params["max_z"]:.2f}')

        if bbx_filters:
            description.append(f'\nBounding Box: {", ".join(bbx_filters)}')

        return f'Applied filters: {", ".join(description)}'

    def RunScript(self,
            Type: str,
            Material: str,
            Dataset: str,
            Complexity: int,
            Fragment: bool,
            MinDimensionX: float,
            MaxDimensionX: float,
            MinDimensionY: float,
            MaxDimensionY: float,
            MinDimensionZ: float,
            MaxDimensionZ: float,
            ComponentData: Grasshopper.DataTree[str]):

        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'Component type filter (e.g., "beam", "slab", "column")'
        )
        self.InputParams[1].Description = (
            'Material type filter (e.g., "concrete", "steel", "wood")'
        )
        self.InputParams[2].Description = (
            'Dataset name filter (e.g., "sas_cita_scans", '
            '"mineral_composite_sheets")'
        )
        self.InputParams[3].Description = (
            'Complexity level filter (0-3, where 0=simple, 3=complex)'
        )
        self.InputParams[4].Description = (
            'Fragment status filter (True for fragments, False for complete)'
        )
        self.InputParams[5].Description = (
            'Minimum X dimension filter (bounding box)'
        )
        self.InputParams[6].Description = (
            'Maximum X dimension filter (bounding box)'
        )
        self.InputParams[7].Description = (
            'Minimum Y dimension filter (bounding box)'
        )
        self.InputParams[8].Description = (
            'Maximum Y dimension filter (bounding box)'
        )
        self.InputParams[9].Description = (
            'Minimum Z dimension filter (bounding box)'
        )
        self.InputParams[10].Description = (
            'Maximum Z dimension filter (bounding box)'
        )
        self.InputParams[11].Description = (
            'Component data to filter (from FetchComponents or similar)'
        )

        # Initialize output param descriptions
        self.OutputParams[0].Description = (
            'Human-readable description of the applied filters'
        )
        self.OutputParams[1].Description = (
            'Filtered ComponentData as JSON strings. Use '
            '\'DisassembleComponent\' to access the individual fields '
            'ready for Grasshopper'
        )

        # Validate input data
        if not ComponentData or ComponentData.DataCount == 0:
            msg = ('No component data provided. '
                   'Please connect ComponentData input.')
            self._addWarning(msg)
            self.Component.Message = msg

            # Return empty results
            FilterDescription = Grasshopper.DataTree[System.Object]()
            FilteredComponentData = Grasshopper.DataTree[System.Object]()
            __Results = (FilterDescription, FilteredComponentData)
            return __Results

        try:
            self.Component.Message = 'Building filter parameters...'

            # Build filter parameters dictionary
            filter_params = {}

            # Add type filter if provided
            if Type and Type.strip() and Type.lower() != 'alltypes':
                filter_params['type'] = Type.strip()

            # Add material filter if provided
            if (Material and Material.strip() and
                    Material.lower() != 'allmaterials'):
                filter_params['material'] = Material.strip()

            # Add dataset filter if provided
            if (Dataset and Dataset.strip() and
                    Dataset.lower() != 'alldatasets'):
                filter_params['dataset'] = Dataset.strip()

            # Add complexity filter if provided
            if Complexity is not None:
                filter_params['complexity'] = Complexity

            # Add fragment filter if provided
            if Fragment is not None:
                filter_params['fragment'] = Fragment

            # Add bounding box filters if provided
            if MinDimensionX is not None and MinDimensionX != 0.0:
                filter_params['min_x'] = MinDimensionX
            if MaxDimensionX is not None and MaxDimensionX != 0.0:
                filter_params['max_x'] = MaxDimensionX
            if MinDimensionY is not None and MinDimensionY != 0.0:
                filter_params['min_y'] = MinDimensionY
            if MaxDimensionY is not None and MaxDimensionY != 0.0:
                filter_params['max_y'] = MaxDimensionY
            if MinDimensionZ is not None and MinDimensionZ != 0.0:
                filter_params['min_z'] = MinDimensionZ
            if MaxDimensionZ is not None and MaxDimensionZ != 0.0:
                filter_params['max_z'] = MaxDimensionZ

            # Generate human-readable filter description
            filter_description = self.generate_filter_description(
                filter_params
            )

            self.Component.Message = 'Filtering components...'

            # Set up output trees and results tuple
            FilterDescription = Grasshopper.DataTree[System.Object]()
            FilteredComponentData = Grasshopper.DataTree[System.Object]()
            __Results = (FilterDescription, FilteredComponentData)

            # Add filter description to the filter query output
            FilterDescription.Add(
                filter_description,
                Grasshopper.Kernel.Data.GH_Path(0))

            # Filter components
            filtered_count = 0
            total_count = 0

            # Loop over all branches
            for i in range(ComponentData.BranchCount):
                ghp = ComponentData.Paths[i]
                for j, comp in enumerate(ComponentData.Branches[i]):
                    total_count += 1
                    try:
                        # Load component data
                        component_data = json.loads(comp)

                        # Apply filters
                        if self.apply_filters(component_data, filter_params):
                            # Component passes all filters, add to output
                            FilteredComponentData.Add(comp, ghp)
                            filtered_count += 1

                    except json.JSONDecodeError as e:
                        msg = f'Failed to parse component data: {str(e)}'
                        self._addWarning(msg)
                        continue
                    except Exception as e:
                        msg = f'Error processing component: {str(e)}'
                        self._addWarning(msg)
                        continue

            # Update component message
            if filtered_count == 0:
                msg = 'No components match the applied filters.'
                self.Component.Message = msg
                self._addWarning(msg)
            else:
                msg = f'Filtered {filtered_count} of {total_count} components.'
                self.Component.Message = msg
                self._addRemark(
                    f'Successfully filtered {filtered_count} components '
                    f'from {total_count} total components'
                )

            return __Results

        except Exception as e:
            msg = f'Unexpected error during filtering: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

            # Return empty results if there was an error
            FilterDescription = Grasshopper.DataTree[System.Object]()
            FilteredComponentData = Grasshopper.DataTree[System.Object]()
            __Results = (FilterDescription, FilteredComponentData)
            return __Results
