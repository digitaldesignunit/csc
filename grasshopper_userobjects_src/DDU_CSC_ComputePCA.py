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

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np  # NOQA
from sklearn.decomposition import PCA  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ComputePCA'  # NOQA
ghenv.Component.NickName = 'ComputePCA'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '6 Data Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Computes principal component analysis (PCA) for dimensionality reduction'
)


class CSC_ComputePCA(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251203
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
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'Data to be reduced using PCA as a DataTree, where '
            'each Branch represents one DataPoint.'
        )
        self.InputParams[1].Description = (
            'Dimension of the embedded space.'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
                'The transformed data as a DataTree, where each Branch '
                'represents one embedded DataPoint.'
            )

    def RunScript(self, Data: Grasshopper.DataTree[float], Components: int):
        # set up output variables
        EmbedddedData = Grasshopper.DataTree[System.Object]()
        try:
            # sanitize input and abort if not present
            self.Component.Message = None
            if not Data or Data.DataCount == 0:
                msg = 'Input Data failed to collect data!'
                self._addWarning(msg)
                return EmbedddedData

            # set defaults for parameters if not provided
            if not Components:
                Components = 2

            # convert all datatree branches to numpy array
            np_data = np.array([np.array(Data.Branch(p)) for p in Data.Paths])

            # initialize t-SNE solver class
            data_reduced = PCA(n_components=Components).fit_transform(np_data)

            # loop over all branches and add embedded data to output tree
            for i in range(len(Data.Branches)):
                EmbedddedData.AddRange(
                    [float(x) for x in data_reduced[i]],
                    Data.Paths[i]
                )

            # return output
            return EmbedddedData

        except Exception as e:
            msg = f'Unexpected error during PCA computation: {str(e)}'
            self._addError(msg)
            return EmbedddedData
