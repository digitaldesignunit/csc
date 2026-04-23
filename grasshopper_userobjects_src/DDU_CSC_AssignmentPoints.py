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

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np  # NOQA
from scipy.optimize import linear_sum_assignment  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'AssignmentPoints'  # NOQA
ghenv.Component.NickName = 'AssignmentPoints'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '5 Matchmaking Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Solve point-to-point assignment between DesignPts and LibraryPts. '
    'Supports Greedy assignment (default, FullCircle-compatible) and '
    'Hungarian assignment (SciPy).'
)

def _weighted_euclidean_distance(pt1, pt2, weights):
    p1 = np.asarray(pt1, dtype=np.float64)
    p2 = np.asarray(pt2, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    return float(np.sqrt(np.sum(w * np.square(p2 - p1))))


class CSC_AssignmentPoints(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260423
    """

    def __init__(self):
        super().__init__()
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg=''):
        self.AddRuntimeMessage(self.Component.RuntimeMessageLevel.Remark, msg)

    def _addWarning(self, msg=''):
        self.AddRuntimeMessage(self.Component.RuntimeMessageLevel.Warning, msg)

    def _addError(self, msg=''):
        self.AddRuntimeMessage(self.Component.RuntimeMessageLevel.Error, msg)

    def BeforeRunScript(self):
        self.InputParams[0].Description = (
            'Design points as DataTree of Numbers. Each branch is one point.'
        )
        self.InputParams[1].Description = (
            'Library points as DataTree of Numbers. Each branch is one point.'
        )
        self.InputParams[2].Description = (
            'Weights for weighted Euclidean distance. Optional; defaults to '
            '1.0 in each dimension.'
        )
        self.InputParams[3].Description = (
            'Scale factor used by Hungarian mode before optimization. '
            'Optional; default 1e3. Ignored by Greedy mode.'
        )
        self.InputParams[4].Description = (
            "Algorithm selector. Optional; defaults to 'greedy'. "
            "Accepted values: 'greedy', 'hungarian'."
        )

        i = 1 if self.OutputParams[0].Name == 'out' else 0
        self.OutputParams[0 + i].Description = (
            'Assignment tree. Branch i contains selected library index for '
            'design point i.'
        )
        self.OutputParams[1 + i].Description = (
            'Assignment cost tree. Branch i contains the cost value for '
            'design point i.'
        )

    def _collect_tree_branches(self, tree):
        if tree is None or tree.DataCount == 0:
            return []
        return [list(tree.Branch(path)) for path in tree.Paths]

    def _normalize_algorithm(self, algorithm):
        if algorithm is None:
            return 'greedy'
        alg = str(algorithm).strip().lower()
        if alg in ('', 'greedy', 'g'):
            return 'greedy'
        if alg in ('hungarian', 'hungary', 'h', 'scipy'):
            return 'hungarian'
        return None

    def _build_cost_matrices(self, design_branches, library_branches, weights):
        n = len(design_branches)
        m = len(library_branches)
        costs = np.zeros((m, m), dtype=np.float64)
        for i in range(m):
            if i >= n:
                continue
            for j in range(m):
                costs[i, j] = _weighted_euclidean_distance(
                    design_branches[i], library_branches[j], weights
                )
        return costs

    def _run_greedy(self, costs):
        m = int(costs.shape[0])
        selected = np.zeros(m, dtype=np.int32)
        assignment = np.full(m, -1, dtype=np.int32)

        for i in range(m):
            min_cost = float('inf')
            sel = -1
            for j in range(m):
                c = float(costs[i, j])
                if c < min_cost and selected[j] == 0:
                    min_cost = c
                    sel = j
            if sel < 0:
                raise ValueError('Greedy assignment failed to select a column')
            selected[sel] = 1
            assignment[i] = sel
        return assignment

    def _run_hungarian(self, costs, scale_factor):
        scaled = np.asarray(
            np.floor(costs * float(scale_factor)),
            dtype=np.int64,
        )
        rows, cols = linear_sum_assignment(scaled)
        assignment = np.full(scaled.shape[0], -1, dtype=np.int32)
        assignment[rows] = cols.astype(np.int32)
        if np.any(assignment < 0):
            raise ValueError('Hungarian assignment did not cover all rows')
        return assignment

    def RunScript(self,
            DesignPts: Grasshopper.DataTree[float],
            LibraryPts: Grasshopper.DataTree[float],
            Weights: System.Collections.Generic.List[float],
            ScaleFactor: float,
            Algorithm: str):
        Assignment = Grasshopper.DataTree[System.Object]()
        Cost = Grasshopper.DataTree[System.Object]()
        __Results = (Assignment, Cost)

        self.Component.Message = None

        design_branches = self._collect_tree_branches(DesignPts)
        library_branches = self._collect_tree_branches(LibraryPts)
        n = len(design_branches)
        m = len(library_branches)

        if n == 0:
            self._addWarning('DesignPts failed to collect data!')
            self.Component.Message = 'no design data'
            return __Results
        if m == 0:
            self._addWarning('LibraryPts failed to collect data!')
            self.Component.Message = 'no library data'
            return __Results
        if n > m:
            self._addError(
                'Number of DesignPts needs to be smaller than number of '
                'LibraryPts!'
            )
            return __Results

        dim = len(design_branches[0])
        if dim == 0:
            self._addError('DesignPts branches are empty')
            return __Results

        for i, b in enumerate(design_branches):
            if len(b) != dim:
                self._addError(
                    f'DesignPts branch #{i} has dimension {len(b)}; '
                    f'expected {dim}.'
                )
                return __Results
        for j, b in enumerate(library_branches):
            if len(b) != dim:
                self._addError(
                    f'LibraryPts branch #{j} has dimension {len(b)}; '
                    f'expected {dim}.'
                )
                return __Results

        if not Weights or len(Weights) == 0:
            weights = np.ones(dim, dtype=np.float64)
        else:
            if len(Weights) != dim:
                self._addError(
                    f'Weights length ({len(Weights)}) does not match point '
                    f'dimension ({dim}).'
                )
                return __Results
            weights = np.asarray([float(w) for w in Weights], dtype=np.float64)

        algorithm = self._normalize_algorithm(Algorithm)
        if algorithm is None:
            self._addError(
                "Invalid Algorithm value. Use 'greedy' or 'hungarian'."
            )
            return __Results

        if ScaleFactor is None:
            ScaleFactor = 1e3
        try:
            scale_factor = float(ScaleFactor)
        except (TypeError, ValueError):
            self._addError(f'ScaleFactor must be numeric, got {ScaleFactor!r}')
            return __Results
        if not np.isfinite(scale_factor) or scale_factor <= 0.0:
            self._addError(f'ScaleFactor must be > 0, got {scale_factor}')
            return __Results

        try:
            real_costs = self._build_cost_matrices(
                design_branches, library_branches, weights
            )
            if algorithm == 'hungarian':
                assignment = self._run_hungarian(real_costs, scale_factor)
                self.Component.Message = 'Hungarian Algorithm'
            else:
                assignment = self._run_greedy(real_costs)
                self.Component.Message = 'Greedy Algorithm'
        except Exception as exc:
            self._addError(f'Assignment failed: {exc}')
            return __Results

        for i in range(n):
            path = Grasshopper.Kernel.Data.GH_Path(i)
            j = int(assignment[i])
            Assignment.Add(j, path)
            Cost.Add(float(real_costs[i, j]), path)

        self._addRemark(
            f'Assigned {n} design points to {m} library points using '
            f'{algorithm}.'
        )
        return __Results
