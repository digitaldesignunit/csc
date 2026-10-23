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
ghenv.Component.Name = 'FetchSimilarComponents'  # NOQA
ghenv.Component.NickName = 'FetchSimilarComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Fetches the components of the remote Catalog that are nearest in shape '
    'to one component by the radial signature (outline and size; not on the '
    '2D Similarity Map), nearest first, as component passport JSON '
    '({identity, snapshots[]}), each with its Distance in standardised '
    'descriptor units (smaller is more similar). Basis: radial_signature '
    '(default), scalars or hks. Takes the filters of FetchFilteredComponents '
    '(they apply before the ranking: the nearest pieces that pass) and the '
    'dimension and near search. The component itself is never one of them.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261022'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.read import (fetch_filter_params, similar_params,  # NOQA
                             similar_results, similar_error_text,
                             fit_mode_of)
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261022 too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('FilterDescription', 'FilterDescription',
     'Human-readable description of the search and the filters applied'),
    ('ComponentPassport', 'ComponentPassport',
     "Component passport JSON per similar component ({identity, snapshots[]}), nearest first. Use 'DisassembleComponent' to access the individual fields ready for Grasshopper"),
    ('Distance', 'Distance',
     'Per result, the distance to the component in the descriptor space of '
     'Basis, in standardised units (each dimension in standard deviations '
     'over the catalog; smaller is more similar, 0 = the same descriptor). '
     'Same paths as ComponentPassport'),
    ('Fit', 'Fit',
     'Dimension search: per result, the deviation in per cent (FitMode '
     'about) or the waste in per cent of the piece (FitMode can_hold). '
     'Empty without FitMode and FitSize. Same paths as ComponentPassport'),
    ('DistanceKm', 'DistanceKm',
     'Near search: per result, the distance in km from NearPoint to the '
     'piece (on NearLayer). Empty without NearPoint. Same paths as '
     'ComponentPassport'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_FetchSimilarComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261022
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
            'The component to find neighbours of: its identity UUID or '
            'component passport JSON',
            'Descriptor space: radial_signature (default: distances from the '
            'centre to the outline or mid-plane section, so outline and '
            'size), scalars (four box, sphere, line and plane scores) or hks '
            '(heat kernel signature)',
            'How many similar components to return (default 10, at most 50)',
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
            'Shape class filter: linear, planar, block, irregular or '
            'composite (derived by the server)',
            'Material class filter, a List of Waste code (e.g. 17 01 01)',
            'Circulation: active (default: in circulation, in place or '
            'deinstalled), in_place (still in the works), deinstalled, '
            'exited or all',
            'Dimension search: about (every side of the piece within '
            'FitTolerance of FitSize) or can_hold (every side of the piece '
            'at least FitSize: a piece to cut your part from). Empty = no '
            'dimension search',
            'The asked size in mm, three numbers in any order (a list of '
            'three numbers, or one Point3d / Vector3d with X, Y, Z). Needs '
            'FitMode',
            'Only for about: a percentage or millimetres as text, 10% or '
            '50mm (a bare number is per cent). Default 10%. can_hold takes '
            'none',
            'Near search: a point with X = latitude and Y = longitude (a '
            'Point3d or Vector3d, as the PlaceLocation of Origin). Empty = '
            'no near search',
            'Near search: current (where the piece is now, default) or '
            'origin (the building it came from)',
            'Near search: only pieces within this many km. Empty = every '
            'piece with a point on the layer',
        ]
        for index, text_ in enumerate(descriptions):
            if index < len(self.InputParams):
                self.InputParams[index].Description = text_
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

    def generate_description(self, identity_id, params) -> str:
        """A human-readable description of the search and its filters."""
        lines = [f'Similar to {identity_id}',
                 f'Basis: {params["basis"]}, up to {params["count"]} '
                 f'components, nearest first']
        for key, label in (('original_function', 'Original function'),
                           ('material', 'Material'),
                           ('dataset', 'Dataset'),
                           ('shape_class', 'Shape class'),
                           ('material_class', 'Material class'),
                           ('circulation', 'Circulation')):
            if params.get(key):
                lines.append(f'{label}: {params[key]}')
        if params.get('complexity') is not None:
            lines.append(f'Complexity: {params["complexity"]}')
        if params.get('fragment') is not None:
            lines.append(f'Fragment: {params["fragment"]}')
        bbx_filters = []
        for axis in 'xyz':
            for kind, sign in (('min', '>='), ('max', '<=')):
                value = params.get(f'bbx_{kind}_{axis}')
                if value is not None:
                    bbx_filters.append(
                        f'{axis.upper()} {sign} {float(value):.2f}')
        if bbx_filters:
            lines.append(f'Bounding Box: {", ".join(bbx_filters)}')
        if params.get('fit_mode') == 'about':
            lines.append(f'Fit: about {params["fit_size"]} mm, within '
                         f'{params["fit_tol"]}')
        elif params.get('fit_mode') == 'can_hold':
            lines.append(f'Fit: can hold {params["fit_size"]} mm')
        if 'near_lat' in params:
            reach = (f', within {params["radius_km"]} km'
                     if 'radius_km' in params else ', nearest first')
            lines.append(f'Near: {params["near_lat"]}, {params["near_lon"]} '
                         f'({params.get("near_layer", "current")} '
                         f'location){reach}')
        return '\n'.join(lines)

    def _refused(self, response, identity_id):
        """Say why a /similar call was refused (404, 409, 422) or failed."""
        status = response.status_code
        detail = None
        try:
            body = response.json()
            detail = body.get('detail') if isinstance(body, dict) else None
        except Exception:
            detail = None
        text = similar_error_text(status, detail)
        if text:
            self._addWarning(text)
        elif status == 401:
            self._addError('Authentication failed. Please sign in again.')
        elif status == 403:
            self._addError('Access denied. Insufficient permissions.')
        elif status == 429:
            self._addWarning('Too many requests. Please wait a moment.')
        elif status >= 500:
            self._addWarning('Server error. Please try again later.')
        else:
            self._addError(f'Request failed with status code: {status}')

    def RunScript(self,
            IdentityID: str,
            Basis: str,
            Count: int,
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
            ShapeClass: str,
            MaterialClass: str,
            Circulation: str,
            FitMode: str,
            FitSize,
            FitTolerance: str,
            NearPoint: Rhino.Geometry.Vector3d,
            NearLayer: str,
            RadiusKm: float):

        if self._stop():
            return empty_outputs()

        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return empty_outputs()
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addWarning(msg)
            return empty_outputs()

        if IdentityID is None or not str(IdentityID).strip():
            self._addWarning('Please provide the identity UUID (or '
                             'component passport JSON) of the component to '
                             'find neighbours of.')
            return empty_outputs()
        identity_id = auth_core.resolve_identity_id_from_input(IdentityID)
        if not identity_id:
            self._addError('IdentityID is not a valid identity UUID or '
                           'component passport JSON.')
            return empty_outputs()

        # the filters, the dimension and near search, the basis and the count
        try:
            filters = fetch_filter_params(
                original_function=OriginalFunction, material=Material,
                dataset=Dataset, complexity=Complexity, fragment=Fragment,
                shape_class=ShapeClass or None,
                material_class=MaterialClass or None,
                circulation=Circulation or None,
                bbx={'min_x': MinDimensionX, 'max_x': MaxDimensionX,
                     'min_y': MinDimensionY, 'max_y': MaxDimensionY,
                     'min_z': MinDimensionZ, 'max_z': MaxDimensionZ},
                fit_mode=FitMode, fit_size=FitSize,
                fit_tolerance=FitTolerance, near_point=NearPoint,
                near_layer=NearLayer, radius_km=RadiusKm)
            params, note = similar_params(filters, Basis, Count)
        except ValueError as e:
            # a basis, count, size, tolerance, point or layer that cannot
            # be used: nothing is sent
            self._addWarning(str(e))
            return empty_outputs()
        if note:
            self._addRemark(note)
        if FitTolerance and fit_mode_of(FitMode) == 'can_hold':
            self._addRemark('FitTolerance is ignored: can_hold takes none')

        try:
            response = auth_core.authorized_get(
                f'/identities/{identity_id}/similar', params, timeout=60)
            if response.status_code != 200:
                self._refused(response, identity_id)
                return empty_outputs()
            body = response.json()
            results = similar_results(body)

            FilterDescription = Grasshopper.DataTree[System.Object]()
            ComponentPassport = Grasshopper.DataTree[System.Object]()
            Distance = Grasshopper.DataTree[System.Object]()
            Fit = Grasshopper.DataTree[System.Object]()
            DistanceKm = Grasshopper.DataTree[System.Object]()
            FilterDescription.Add(
                self.generate_description(identity_id, params),
                Grasshopper.Kernel.Data.GH_Path(0))

            lost = 0
            for item in results:
                # the passport of each neighbour, as the other Fetch
                # components build them (cached by the Session)
                passport = auth_core.cached_get_passport(item['id'])
                if passport.status_code != 200:
                    lost += 1
                    continue
                # paths count the found passports only: no gap for a lost
                # one, and Distance, Fit and DistanceKm share the paths
                ghp = Grasshopper.Kernel.Data.GH_Path(
                    0, ComponentPassport.DataCount)
                ComponentPassport.Add(
                    auth_core.passport_json_string(passport.json()), ghp)
                Distance.Add(item['distance'], ghp)
                if item['fit'] is not None:
                    Fit.Add(item['fit'], ghp)
                if item['distance_km'] is not None:
                    DistanceKm.Add(item['distance_km'], ghp)

            found = ComponentPassport.DataCount
            self._state(f'{found} similar')
            self._addRemark(
                f'Found {found} similar components among '
                f'{body.get("considered", "?")} compared '
                f'({body.get("basis_label", params["basis"])})')
            if lost:
                self._addWarning(
                    f'{lost} similar components could not be fetched '
                    f'(passport not available)')
            return (FilterDescription, ComponentPassport, Distance, Fit,
                    DistanceKm)

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
        FilterDescription = Grasshopper.DataTree[System.Object]()
        ComponentPassport = Grasshopper.DataTree[System.Object]()
        Distance = Grasshopper.DataTree[System.Object]()
        Fit = Grasshopper.DataTree[System.Object]()
        DistanceKm = Grasshopper.DataTree[System.Object]()
        return (FilterDescription, ComponentPassport, Distance, Fit,
                DistanceKm)
