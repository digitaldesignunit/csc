#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: numpy==2.0.2
# r: d2p-core-py==0.1.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# D2P WRAPPER IMPORTS ---------------------------------------------------------
from d2p_core.utility.instantiation import instance_from_object  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ReadFromD2P'  # NOQA
ghenv.Component.NickName = 'ReadFromD2P'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '9 D2P Components Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Reads the elements of the active Rhino document back into component '
    'passport JSON. A D2P component (made by PassportToD2P and committed '
    'with D2P) is read from the user text of its members, with the placement '
    'from the plane of the D2P component now. An element baked by '
    'BakeComponents is read from its tag; a bake is not a D2P component, so '
    'its Component output is null. The component passport comes from the '
    'stored csc_component or by id through the Session. Nothing is written '
    'to the server.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261102'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.doc import (net_instance, net_type_name, passport_fetcher, read_document)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261102 too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('ComponentPassport', 'ComponentPassport',
     'DataTree of component passport JSON ({identity, snapshots[]}), one per element, with csc_placement set from the plane of the D2P component (or the tag, for an element baked by BakeComponents)'),
    ('Component', 'Component',
     'The D2P component of each component passport (.NET IComponentBase), for elements made by PassportToD2P and committed with D2P. Null for an element baked by BakeComponents: a bake is a tag with its geometry, not a D2P component'),
]


def empty_outputs():
    """What RunScript returns when it stops early or has no result: an empty
    Grasshopper tree per output (never '' or None)."""
    if not OUTPUTS:
        return None
    trees = tuple(Grasshopper.DataTree[System.Object]() for _ in OUTPUTS)
    return trees[0] if len(trees) == 1 else trees


class CSC_ReadFromD2P(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261102
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        self.Component = ghenv.Component  # NOQA
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
        self.InputParams[0].Description = (
            'Trigger to read the D2P components of the Rhino document'
        )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self, Read: bool):
        if self._stop():
            return empty_outputs()
        ComponentPassport = Grasshopper.DataTree[str]()
        Component = Grasshopper.DataTree[System.Object]()
        if not Read:
            self._state('Read is off')
            return ComponentPassport, Component
        try:
            doc = Rhino.RhinoDoc.ActiveDoc
            found = {}
            failed = []

            def d2p_plane(entry):
                """The plane of the D2P component the label belongs to."""
                # a D2P label is named like its component; a plain tag of
                # BakeComponents has no name and is not asked
                if not entry['object'].Attributes.Name:
                    return None
                try:
                    component = instance_from_object(entry['object'])
                    plane = None if component is None else component.Plane
                except Exception as error:
                    failed.append((entry['object'].Id, error))
                    return None
                if component is None:
                    return None
                # the output carries the concrete .NET object (IComponentBase)
                # that D2P and Grasshopper accept, as PassportToD2P does
                found[entry['object'].Id] = net_instance(component)
                return plane

            fetch = passport_fetcher(sc.sticky.get('CSC_AuthCore'))
            pieces = read_document(doc, fetch, d2p_plane)
            if not pieces:
                msg = 'No CSC components found in the document!'
                self._addWarning(msg)
                return ComponentPassport, Component

            errors = dict(failed)
            put_out = []
            for i, piece in enumerate(pieces):
                label = piece['identity_id'] or 'a tag without an identity'
                for problem in piece['problems']:
                    self._addWarning(f'{label}: {problem}')
                if piece['object'].Id in errors:
                    self._addWarning(
                        f'{label}: the D2P component could not be resolved '
                        f'({errors[piece["object"].Id]}); its Component is '
                        'null and the placement is read from the tag')
                if piece['passport'] is None:
                    continue
                ghp = Grasshopper.Kernel.Data.GH_Path(i)
                ComponentPassport.Add(json.dumps(piece['passport']), ghp)
                d2p_component = found.get(piece['object'].Id)
                Component.Add(d2p_component, ghp)
                if d2p_component is not None:
                    put_out.append(d2p_component)
                self._addRemark(f'Read {label}')

            types = sorted({net_type_name(c) for c in put_out})
            if types:
                self._addRemark(
                    f'Component: {len(put_out)} D2P component(s) as '
                    f'{", ".join(types)}')
            self._state(f'Read {ComponentPassport.DataCount}')
            return ComponentPassport, Component

        except Exception as error:
            msg = f'Unexpected error reading the document: {error}'
            self._addError(msg)
            return ComponentPassport, Component
