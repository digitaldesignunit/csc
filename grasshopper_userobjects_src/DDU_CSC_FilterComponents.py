#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: numpy==2.0.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FilterComponents'  # NOQA
ghenv.Component.NickName = 'FilterComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Filters a list of component passport JSON entries ({identity, snapshots[]}) based '
    'on various criteria (original function, material, dataset, complexity, '
    'fragment, bounding box dimensions, shape class, material class). Works '
    'with local component passport data from fetch components.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.read import (passes_filters)  # NOQA
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
     'Human-readable description of the applied filters'),
    ('FilteredComponentPassports', 'FilteredComponentPassports',
     "Filtered component passport JSON strings ({identity, snapshots[]}). Use 'DisassembleComponent' to access the individual fields ready for Grasshopper"),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_FilterComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005
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
            'Shape class filter: linear, planar, block, irregular or '
            'composite',
            'Material class filter, a List of Waste code (e.g. 17 01 01)',
            'Component passport JSON strings to filter ({identity, snapshots[]}), '
            'e.g. from FetchAllComponents, FetchComponents, or '
            'FetchFilteredComponents',
        ]
        for index, text_ in enumerate(descriptions):
            if index < len(self.InputParams):
                self.InputParams[index].Description = text_
        # Initialize output param descriptions
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def apply_filters(self, passport: dict, filter_params: dict) -> bool:
        """
        Apply all filters to a single passport entry (csc_read): identity
        fields (original function, material, dataset, material class) and
        snapshot fields (shape class, complexity, fragment, bbx).
        """
        bbx = {key: filter_params.get(key) for key in (
            'min_x', 'max_x', 'min_y', 'max_y', 'min_z', 'max_z')}
        return passes_filters(
            passport,
            original_function=filter_params.get('original_function'),
            material=filter_params.get('material'),
            dataset=filter_params.get('dataset'),
            complexity=filter_params.get('complexity'),
            fragment=filter_params.get('fragment'),
            shape_class=filter_params.get('shape_class'),
            material_class=filter_params.get('material_class'),
            bbx=bbx)

    def generate_filter_description(self, filter_params: dict) -> str:
        """Generates a human-readable description of the applied filters."""
        description = []
        if filter_params.get('original_function'):
            description.append(
                f'\nOriginal function: {filter_params["original_function"]}')
        if filter_params.get('shape_class'):
            description.append(
                f'\nShape class: {filter_params["shape_class"]}')
        if filter_params.get('material_class'):
            description.append(
                f'\nMaterial class: {filter_params["material_class"]}')
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
            ComponentPassport: Grasshopper.DataTree[object]):
        # Validate input data
        if self._stop():
            return empty_outputs()
        if not ComponentPassport or ComponentPassport.DataCount == 0:
            msg = ('No component passport data provided. '
                   'Please connect ComponentPassport input.')
            self._addWarning(msg)

            # Return empty results
            FilterDescription = Grasshopper.DataTree[System.Object]()
            FilteredComponentPassports = Grasshopper.DataTree[System.Object]()
            __Results = (FilterDescription, FilteredComponentPassports)
            return __Results

        try:

            # Build filter parameters dictionary
            filter_params = {}

            # Add original function filter if provided
            if (OriginalFunction and OriginalFunction.strip()
                    and OriginalFunction.lower() != 'alltypes'):
                filter_params['original_function'] = OriginalFunction.strip()

            if ShapeClass and ShapeClass.strip():
                filter_params['shape_class'] = ShapeClass.strip()
            if MaterialClass and MaterialClass.strip():
                filter_params['material_class'] = MaterialClass.strip()

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


            # Set up output trees and results tuple
            FilterDescription = Grasshopper.DataTree[System.Object]()
            FilteredComponentPassports = Grasshopper.DataTree[System.Object]()
            __Results = (FilterDescription, FilteredComponentPassports)

            # Add filter description to the filter query output
            FilterDescription.Add(
                filter_description,
                Grasshopper.Kernel.Data.GH_Path(0))

            # Filter components
            filtered_count = 0
            total_count = 0

            # Loop over all branches
            for i in range(ComponentPassport.BranchCount):
                ghp = ComponentPassport.Paths[i]
                for j, comp in enumerate(ComponentPassport.Branches[i]):
                    total_count += 1
                    try:
                        # Load passport JSON
                        passport = json.loads(comp)
                        identity = passport.get('identity')
                        snapshots = passport.get('snapshots') or []
                        snapshot = snapshots[0] if snapshots else None
                        if not isinstance(identity, dict) or not isinstance(
                                snapshot, dict):
                            self._addWarning(
                                'Skipping entry: not component passport JSON '
                                '({identity, snapshot})')
                            continue

                        # Apply filters
                        if self.apply_filters(passport, filter_params):
                            # Entry passes all filters, add to output
                            FilteredComponentPassports.Add(comp, ghp)
                            filtered_count += 1

                    except json.JSONDecodeError as e:
                        msg = f'Failed to parse component passport JSON: {str(e)}'
                        self._addWarning(msg)
                        continue
                    except Exception as e:
                        msg = f'Error processing component: {str(e)}'
                        self._addWarning(msg)
                        continue

            # Update component message
            if filtered_count == 0:
                msg = 'No components match the applied filters.'
                self._addWarning(msg)
            else:
                msg = f'Filtered {filtered_count} of {total_count} components.'
                self._addRemark(
                    f'Successfully filtered {filtered_count} components '
                    f'from {total_count} total components'
                )

            return __Results

        except Exception as e:
            msg = f'Unexpected error during filtering: {str(e)}'
            self._addError(msg)

            # Return empty results if there was an error
            FilterDescription = Grasshopper.DataTree[System.Object]()
            FilteredComponentPassports = Grasshopper.DataTree[System.Object]()
            __Results = (FilterDescription, FilteredComponentPassports)
            return __Results
