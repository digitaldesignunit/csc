#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS
import json

# .NET RHINO IMPORTS
import System
import Rhino
import Grasshopper


# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "FilterComponents"
ghenv.Component.NickName = "FilterComponents"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "2 Catalogue Interface"


class CSC_FilterComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250820
    """

    def RunScript(self,
            Type: str,
            Material: str,
            DimensionX: float,
            DimensionY: float,
            DimensionZ: float,
            ComponentData: Grasshopper.DataTree[str]):

        FilteredComponentData = Grasshopper.DataTree[System.Object]()

        Type = str(Type)
        Material = str(Material)
        DimensionX = float(DimensionX)
        DimensionY = float(DimensionY)
        DimensionZ = float(DimensionZ)

        if not ComponentData:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input ComponentData failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return FilteredComponentData

        # loop over all branches
        for i in range(ComponentData.BranchCount):
            ghp = Grasshopper.Kernel.Data.GH_Path(i)
            for j, comp in enumerate(ComponentData.Branches[i]):
                # load component
                jcomp = json.loads(comp)
                # filter component
                if Type != 'alltypes':
                    if jcomp['type'] != Type:
                        continue
                if Material != 'allmaterials':
                    if jcomp['material'] != Material:
                        continue
                bbx_min = jcomp['bbx'][0]
                bbx_max = jcomp['bbx'][1]
                if DimensionX > 0:
                    dimx = bbx_max[0] - bbx_min[0]
                    if dimx > DimensionX:
                        continue
                if DimensionY > 0:
                    dimy = bbx_max[1] - bbx_min[1]
                    if dimy > DimensionY:
                        continue
                if DimensionZ > 0:
                    dimz = bbx_max[2] - bbx_min[2]
                    if dimz > DimensionZ:
                        continue
                FilteredComponentData.Add(json.dumps(jcomp), ghp)
        # return results
        return FilteredComponentData
