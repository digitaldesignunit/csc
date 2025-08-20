#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

import json

import System
import Rhino
import Grasshopper
import rhinoscriptsyntax as rs
import scriptcontext as sc

# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "CSC_SyncWithRhinoDoc"
ghenv.Component.NickName = "CSC_SyncWithRhinoDoc"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "3 Component Operations"


class SyncWithRhinoDoc(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250820
    """

    LAST_SYNC = Grasshopper.DataTree[object]()

    def RunScript(self, Sync: bool):
        # set sc doc to rhino doc
        sc.doc = Rhino.RhinoDoc.ActiveDoc

        if Sync:
            lay_parent = 'CSC_COMPONENTS'
            self.LAST_SYNC = Grasshopper.DataTree[object]()
            # get layers
            if rs.IsLayer(lay_parent):
                comp_lays = rs.LayerChildren(lay_parent)
                # loop over all layers
                for i, lay in enumerate(comp_lays):
                    ghp = Grasshopper.Kernel.Data.GH_Path(i)
                    # retrieve objects on layer
                    objects = rs.ObjectsByLayer(lay)
                    for o in objects:
                        if rs.IsText(o):
                            tagplane = rs.coercegeometry(o).Plane
                            tagframe = {
                                'o': [tagplane.OriginX,
                                      tagplane.OriginY,
                                      tagplane.OriginZ],
                                'x': [tagplane.XAxis.X,
                                      tagplane.XAxis.Y,
                                      tagplane.XAxis.Z],
                                'y': [tagplane.YAxis.X,
                                      tagplane.YAxis.Y,
                                      tagplane.YAxis.Z],
                                'z': [tagplane.ZAxis.X,
                                      tagplane.ZAxis.Y,
                                      tagplane.ZAxis.Z]
                            }
                            data = rs.GetUserText(o, 'componentdata')
                            data_obj = json.loads(data)
                            data_obj['iframe'].update(tagframe)
                            data = json.dumps(data_obj)
                            self.LAST_SYNC.Add(data, ghp)
        if self.LAST_SYNC.DataCount < 1:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Document out of Sync or no Components in Document!'
            print(msg)
            ghenv.Component.AddRuntimeMessage(rml, msg)
        
        sc.doc = ghdoc
        return self.LAST_SYNC