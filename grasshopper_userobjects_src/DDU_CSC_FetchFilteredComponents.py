#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: requests==2.32.5
# r: numpy==2.0.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FetchFilteredComponents'  # NOQA
ghenv.Component.NickName = 'FetchFilteredComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Fetches identities (with their current snapshot) from the remote '
    'Catalog based on filter criteria (original function, material, '
    'dataset, complexity, fragment, bounding box dimensions, shape class, '
    'material class, circulation). Mirrors the web catalog filter menu and '
    'returns component passport JSON ({identity, snapshots[]}) results.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.read import (fetch_filter_params)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261005 too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('FilterDescription', 'FilterDescription',
     'Human-readable description of the applied filters and query'),
    ('ComponentPassport', 'ComponentPassport',
     "Component passport JSON per entry ({identity, snapshots[]}) fetched from the server. Use 'DisassembleComponent' to access the individual fields ready for Grasshopper"),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_FetchFilteredComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005a
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

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

    def _state(self, text=''):
        """The one short state under the component (decision 8.113)."""
        if set_state is not None:
            set_state(self.Component, text)

    def _stop(self):
        """True when RunScript has to return early: the library is missing or
        too old, or the outputs were just updated (says why)."""
        if LIBRARY_PROBLEM:
            self._addError(LIBRARY_PROBLEM)
            return True
        if self._outputs_note:
            self._addRemark(self._outputs_note)
        return not self._outputs_ready

    def _check_outputs(self):
        """Make the outputs match OUTPUTS before the script runs (8.112)."""
        self._outputs_ready, self._outputs_note = True, None
        if ensure_outputs is None:
            self._outputs_note = (
                'output check skipped: CSC library not installed')
            return
        status = ensure_outputs(self.Component, OUTPUTS)
        self._outputs_ready, self._outputs_note = status.ready, status.remark

    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        descriptions = [
            'Original function filter, an IFC class (e.g. IfcBeam, '
            'IfcColumn, IfcSlab, IfcPlate, CscDebris)',
            'Material filter, a material id (e.g. concrete, steel, timber)',
            'Dataset name filter (e.g., "beyond_debris", '
            '"mineral_composite_sheets")',
            'Complexity level filter (0-3, where 0=simple, 3=complex)',
            'Fragment status filter (True for fragments, False for complete)',
            'Minimum X dimension filter (bounding box, longest side)',
            'Maximum X dimension filter (bounding box)',
            'Minimum Y dimension filter (bounding box)',
            'Maximum Y dimension filter (bounding box)',
            'Minimum Z dimension filter (bounding box, shortest side)',
            'Maximum Z dimension filter (bounding box)',
            'Reservation status filter: -1=ignore, 0=not reserved, '
            '1=reserved by current user',
            'Shape class filter: linear, planar, block, irregular or '
            'composite (derived by the server)',
            'Material class filter, a List of Waste code (e.g. 17 01 01)',
            'Circulation: active (default: in circulation, in place or '
            'deinstalled), in_place (still in the works), deinstalled, '
            'exited or all',
        ]
        for index, text_ in enumerate(descriptions):
            if index < len(self.InputParams):
                self.InputParams[index].Description = text_
        # Initialize output param descriptions
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addWarning(msg)
            return None
        return auth_core

    def build_filter_query_params(
            self,
            OriginalFunction,
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
            ReservedStatus,
            ShapeClass,
            MaterialClass,
            Circulation):
        """
        Build query parameters for GET /identities (csc_read).

        Mirrors the web catalog filter menu: original function, material,
        dataset, complexity, fragment, bounding box, shape class, material
        class and circulation. ``status`` is left to the server default
        (published only), matching the web. Adds a reservation-status filter
        on top: 1=reserved by current user, 0=not reserved.
        """
        function = OriginalFunction
        if isinstance(function, (list, tuple)):
            function = function[0] if function else None
        return fetch_filter_params(
            original_function=function,
            material=Material, dataset=Dataset, complexity=Complexity,
            fragment=Fragment, reserved=ReservedStatus,
            shape_class=ShapeClass, material_class=MaterialClass,
            circulation=Circulation,
            bbx={'min_x': MinDimensionX, 'max_x': MaxDimensionX,
                 'min_y': MinDimensionY, 'max_y': MaxDimensionY,
                 'min_z': MinDimensionZ, 'max_z': MaxDimensionZ})

    def generate_filter_description(self, filter_params: dict) -> str:
        """Generates a human-readable description of the applied filters."""
        description = []
        for key, label in (('original_function', 'Original function'),
                           ('material', 'Material'),
                           ('dataset', 'Dataset'),
                           ('shape_class', 'Shape class'),
                           ('material_class', 'Material class'),
                           ('circulation', 'Circulation')):
            if filter_params.get(key):
                description.append(f'\n{label}: {filter_params[key]}')
        if filter_params.get('complexity') is not None:
            description.append(f'\nComplexity: {filter_params["complexity"]}')
        if filter_params.get('fragment') is not None:
            description.append(f'\nFragment: {filter_params["fragment"]}')
        if filter_params.get('reserved') == 'false':
            description.append('\nReservation: Not reserved by anyone')
        elif filter_params.get('reserved') == 'true':
            description.append('\nReservation: Reserved by current user')
        bbx_filters = []
        for axis in 'xyz':
            for kind, sign in (('min', '>='), ('max', '<=')):
                value = filter_params.get(f'bbx_{kind}_{axis}')
                if value is not None:
                    bbx_filters.append(
                        f'\n{axis.upper()} {sign} {float(value):.2f}')
        if bbx_filters:
            description.append(f'\nBounding Box: {", ".join(bbx_filters)}')
        return f'Applied filters: {", ".join(description)}'

    def RunScript(self,
            OriginalFunction: str,
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
            ReservedStatus,
            ShapeClass: str,
            MaterialClass: str,
            Circulation: str):

        if self._stop():
            return empty_outputs()
        if not ShapeClass or ShapeClass == '':
            ShapeClass = None
        if not MaterialClass or MaterialClass == '':
            MaterialClass = None
        if not Circulation or Circulation == '':
            Circulation = None

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return empty_outputs()

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addWarning(msg)
            return empty_outputs()

        try:

            # Build filter query parameters (parity with web filter menu)
            filter_params = self.build_filter_query_params(
                OriginalFunction, Material, Dataset, Complexity, Fragment,
                MinDimensionX, MaxDimensionX, MinDimensionY,
                MaxDimensionY, MinDimensionZ, MaxDimensionZ,
                ReservedStatus, ShapeClass, MaterialClass, Circulation
            )

            # Request params: filters + passport expansion (identity+snapshot)
            request_params = dict(filter_params)
            request_params['expand'] = 'current_snapshot'

            # Generate human-readable filter description
            filter_description = self.generate_filter_description(
                filter_params
            )


            # Unified catalog cache (same identity/snapshot store as
            # FetchAllComponents and FetchComponents).
            response = auth_core.cached_list_identities(request_params)

            if response.status_code == 200:
                # Successfully fetched passport entries
                json_comps = response.json()
                component_count = len(json_comps)

                self._state(f'{component_count} found')

                self._addRemark(
                    f'Successfully fetched {component_count} components '
                    f'with applied filters'
                )

                # Set up output trees and results tuple
                FilterDescription = Grasshopper.DataTree[System.Object]()
                ComponentPassport = Grasshopper.DataTree[System.Object]()
                __Results = (FilterDescription, ComponentPassport)

                # Loop over all passport entries and add them to the data tree
                for i, json_comp in enumerate(json_comps):
                    # Create datatree path
                    ghp = Grasshopper.Kernel.Data.GH_Path(0, i)
                    # Add passport JSON to the datatree
                    ComponentPassport.Add(
                        auth_core.passport_json_string(json_comp), ghp)

                # Add filter description to the filter query output
                FilterDescription.Add(
                    filter_description,
                    Grasshopper.Kernel.Data.GH_Path(0)
                )

                return __Results

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)

            elif response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
                self._addError(msg)

            elif response.status_code == 500:
                msg = 'Server error. Please try again later.'
                self._addWarning(msg)

            else:
                msg = (f'Request failed with status code: '
                       f'{response.status_code}')
                self._addError(msg)

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

        # Return empty results if there was an error
        ComponentPassport = Grasshopper.DataTree[System.Object]()
        FilterDescription = Grasshopper.DataTree[System.Object]()
        __Results = (FilterDescription, ComponentPassport)
        return __Results
