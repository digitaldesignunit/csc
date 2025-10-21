#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
from sklearn.manifold import TSNE

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ComputeTSNE'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'ComputeTSNE'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '7 Geometry Tools'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Computes T-distributed Stochastic Neighbor Embedding.'
)


class CSC_ComputeTSNE(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251021
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

    def RunScript(self,
            Data: Grasshopper.DataTree[float],
            Components: int,
            Perplexity: int,
            EarlyExaggeration: float,
            LearningRate: float,
            Iterations: int,
            Method: int,
            Initialization: int,
            RandomSeed: int):
        # set up output variables
        EmbedddedData = Grasshopper.DataTree[System.Object]()

        try:
            # Initialize param descriptions (this has to be done in RunScript)
            self.InputParams[0].Description = (
                'Data to be reduced using t-SNE as a DataTree, where '
                'each Branch represents one DataPoint.'
            )
            self.InputParams[1].Description = (
                'Dimension of the embedded space.'
            )
            self.InputParams[2].Description = (
                'The perplexity is related to the number of nearest neighbors '
                'that are used in other manifold learning algorithms. '
                'Consider selecting a value between 5 and 50. Defaults to 30.'
            )
            self.InputParams[3].Description = (
                'Controls how tight natural clusters in the original space '
                'are in the embedded space and how much space will be '
                'between them.'
                'Defaults to 12.'
            )
            self.InputParams[4].Description = (
                'The learning rate for t-SNE is usually in the range '
                '(10.0, 1000.0).'
                'Defaults to 200.'
            )
            self.InputParams[5].Description = (
                'Maximum number of iterations for the optimization. '
                'Should be at least 250.'
                'Defaults to 1000.'
            )
            self.InputParams[6].Description = (
                'Barnes-Hut approximation (0) runs in O(NlogN) time. '
                'Exact method (1) will run on the slower, but exact, '
                'algorithm in O(N^2) time.'
                'Defaults to 0.'
            )
            self.InputParams[7].Description = (
                'Initialization method. Random (0) or PCA (1).'
                'Defaults to 0.'
            )
            self.InputParams[8].Description = (
                'Determines the random number generator. Pass an int for '
                'reproducible results across multiple function calls. '
                'Note that different initializations might result in '
                'different local minima of the cost function.'
                'Defaults to None.'
            )
            # Initialize output param descriptions
            self.OutputParams[0].Description = (
                'The transformed data as a DataTree, where each Branch '
                'represents one embeddedDataPoint.'
            )

            # sanitize input and abort if not present
            self.Component.Message = None
            if not Data:
                msg = 'Input Data failed to collect data!'
                self._addWarning(msg)
                return EmbedddedData

            # set defaults for parameters if not provided
            if not Components:
                Components = 2
            if not Perplexity:
                Perplexity = 30
            if not EarlyExaggeration:
                EarlyExaggeration = 12.0
            if not LearningRate:
                LearningRate = 200.0
            if not Iterations:
                Iterations = 1000
            if not Method:
                Method = 0
            if not Initialization:
                Initialization = 0
            if not RandomSeed:
                RandomSeed = 0

            # convert method string
            if Method <= 0:
                method_str = "barnes_hut"
            else:
                method_str = "exact"
            if Initialization <= 0:
                init_str = "random"
            else:
                init_str = "pca"

            # convert all datatree branches to numpy array
            np_data = np.array([np.array(Data.Branch(p)) for p in Data.Paths])

            # initialize t-SNE solver class
            tsne = TSNE(n_components=Components,
                        perplexity=Perplexity,
                        early_exaggeration=EarlyExaggeration,
                        learning_rate=LearningRate,
                        n_iter=Iterations,
                        random_state=RandomSeed,
                        method=method_str,
                        init=init_str)

            # run t-SNE solver on incoming data
            tsne_result = tsne.fit_transform(np_data)

            # loop over all branches and add embedded data to output tree
            for i in range(len(Data.Branches)):
                EmbedddedData.AddRange(
                    [float(x) for x in tsne_result[i]],
                    Data.Paths[i]
                )

            # return output
            return EmbedddedData

        except Exception as e:
            msg = f'Unexpected error during t-SNE computation: {str(e)}'
            self._addError(msg)
            return EmbedddedData
