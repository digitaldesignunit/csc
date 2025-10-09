#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FetchFilteredComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'FetchFilteredComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_FetchFilteredComponents(Grasshopper.Kernel.GH_ScriptInstance):
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
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_SignIn component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def build_filter_query_params(
            self,
            Type,
            Material,
            Dataset,
            Complexity,
            Fragment,
            MinDimensionX,
            MaxDimensionX,
            MinDimensionY,
            MaxDimensionY,
            MinDimensionZ,
            MaxDimensionZ,
            ReservedStatus):
        """Build query parameters for filtering components."""
        params = {}

        # Add type filter if provided
        if Type and len(Type) > 0:
            # Take the first type if multiple are provided
            type_value = Type[0] if isinstance(Type, list) else str(Type)
            if type_value and type_value.strip():
                params['comptype'] = type_value.strip()

        # Add material filter if provided
        if Material and Material.strip():
            params['material'] = Material.strip()

        # Add dataset filter if provided
        if Dataset and Dataset.strip():
            params['dataset'] = Dataset.strip()

        # Add complexity filter if provided
        if Complexity is not None:
            params['complexity'] = Complexity

        # Add fragment filter if provided
        if Fragment is not None:
            params['fragment'] = Fragment

        # Add reservation status filter if provided
        if ReservedStatus is not None and ReservedStatus != -1:
            if ReservedStatus == 0:
                # Fetch components that are not reserved by anyone
                params['reserved'] = 'false'
            elif ReservedStatus == 1:
                # Fetch components reserved by current user
                params['reserved'] = 'true'

        # Add bounding box filters if provided
        if MinDimensionX is not None and MinDimensionX != 0.0:
            params['bbx_min_x'] = MinDimensionX
        if MaxDimensionX is not None and MaxDimensionX != 0.0:
            params['bbx_max_x'] = MaxDimensionX
        if MinDimensionY is not None and MinDimensionY != 0.0:
            params['bbx_min_y'] = MinDimensionY
        if MaxDimensionY is not None and MaxDimensionY != 0.0:
            params['bbx_max_y'] = MaxDimensionY
        if MinDimensionZ is not None and MinDimensionZ != 0.0:
            params['bbx_min_z'] = MinDimensionZ
        if MaxDimensionZ is not None and MaxDimensionZ != 0.0:
            params['bbx_max_z'] = MaxDimensionZ

        return params

    def generate_filter_description(self, filter_params: dict) -> str:
        """Generates a human-readable description of the applied filters."""
        description = []
        if filter_params.get('comptype'):
            description.append(f'\nType: {filter_params["comptype"]}')
        if filter_params.get('material'):
            description.append(f'\nMaterial: {filter_params["material"]}')
        if filter_params.get('dataset'):
            description.append(f'\nDataset: {filter_params["dataset"]}')
        if filter_params.get('complexity') is not None:
            description.append(f'\nComplexity: {filter_params["complexity"]}')
        if filter_params.get('fragment') is not None:
            description.append(f'\nFragment: {filter_params["fragment"]}')

        # Add reservation status filter description
        if filter_params.get('reserved') == 'false':
            description.append('\nReservation: Not reserved by anyone')
        elif filter_params.get('reserved') == 'true':
            description.append('\nReservation: Reserved by current user')

        # Handle bounding box filters with detailed information
        bbx_filters = []
        if filter_params.get('bbx_min_x') is not None:
            bbx_filters.append(f'\nX >= {filter_params["bbx_min_x"]:.2f}')
        if filter_params.get('bbx_max_x') is not None:
            bbx_filters.append(f'\nX <= {filter_params["bbx_max_x"]:.2f}')
        if filter_params.get('bbx_min_y') is not None:
            bbx_filters.append(f'\nY >= {filter_params["bbx_min_y"]:.2f}')
        if filter_params.get('bbx_max_y') is not None:
            bbx_filters.append(f'\nY <= {filter_params["bbx_max_y"]:.2f}')
        if filter_params.get('bbx_min_z') is not None:
            bbx_filters.append(f'\nZ >= {filter_params["bbx_min_z"]:.2f}')
        if filter_params.get('bbx_max_z') is not None:
            bbx_filters.append(f'\nZ <= {filter_params["bbx_max_z"]:.2f}')

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
            ReservedStatus):
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
            'Reservation status filter: -1=ignore, 0=not reserved, '
            '1=reserved by current user'
        )

        # Initialize output param descriptions
        self.OutputParams[0].Description = (
            'Human-readable description of the applied filters and query'
        )
        self.OutputParams[1].Description = (
            'The ComponentData that was fetched from the server as JSON. '
            'Use \'DisassembleComponent\' to access the individual fields '
            'ready for Grasshopper')

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_SignIn '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return

        try:
            self.Component.Message = 'Building filter query...'

            # Build filter query parameters
            filter_params = self.build_filter_query_params(
                Type, Material, Dataset, Complexity, Fragment,
                MinDimensionX, MaxDimensionX, MinDimensionY,
                MaxDimensionY, MinDimensionZ, MaxDimensionZ,
                ReservedStatus
            )

            # Build the query string
            query_string = '&'.join([
                f'{k}={v}' for k, v in filter_params.items()
            ])
            endpoint = '/components'
            if query_string:
                endpoint += f'?{query_string}'

            # Generate human-readable filter description
            filter_description = self.generate_filter_description(
                filter_params
            )

            self.Component.Message = (
                'Fetching filtered components (with cache)...'
            )

            # Create cache key based on filter parameters
            cache_key = (f'filtered:{query_string}' if query_string
                         else 'filtered:all')
            # Make cached request to fetch filtered components
            response = auth_core.cached_get(endpoint, cache_key, filter_params)

            if response.status_code == 200:
                # Successfully fetched components
                json_comps = response.json()
                component_count = len(json_comps)

                # Show filter info in message
                filter_msg = f'Found {component_count} components (cached).'

                self.Component.Message = filter_msg
                self._addRemark(
                    f'Successfully fetched {component_count} components '
                    f'with applied filters'
                )

                # Set up output trees and results tuple
                FilterDescription = Grasshopper.DataTree[System.Object]()
                ComponentData = Grasshopper.DataTree[System.Object]()
                __Results = (FilterDescription, ComponentData)

                # Loop over all components and add them to the data tree
                for i, json_comp in enumerate(json_comps):
                    # Create datatree path
                    ghp = Grasshopper.Kernel.Data.GH_Path(i)
                    # Add component data to the datatree
                    ComponentData.Add(json.dumps(json_comp), ghp)

                # Add filter description to the filter query output
                FilterDescription.Add(
                    filter_description,
                    Grasshopper.Kernel.Data.GH_Path(0)
                )

                return __Results

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 500:
                msg = 'Server error. Please try again later.'
                self._addWarning(msg)
                self.Component.Message = msg

            else:
                msg = (f'Request failed with status code: '
                       f'{response.status_code}')
                self._addError(msg)
                self.Component.Message = msg

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

        # Return empty results if there was an error
        ComponentData = Grasshopper.DataTree[System.Object]()
        FilterDescription = Grasshopper.DataTree[System.Object]()
        __Results = (FilterDescription, ComponentData)
        return __Results
