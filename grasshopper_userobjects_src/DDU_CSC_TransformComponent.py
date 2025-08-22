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


# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "TransformComponent"
ghenv.Component.NickName = "TransformComponent"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "3 Component Operations"


class CSC_TransformComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250820
    """

    def ComponentPolyline(self, jcomp: dict) -> Rhino.Geometry.Polyline:
        pl = Rhino.Geometry.Polyline()
        pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
               for pt in jcomp['geometry']['polyline']]
        pl.AddRange(pts)
        return pl

    def ComponentPolylineExtrusion(self, jcomp: dict) -> Rhino.Geometry.Extrusion:
        pl = Rhino.Geometry.Polyline()
        pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
               for pt in jcomp['geometry']['polyline']]
        pl.AddRange(pts)
        cxt = Rhino.Geometry.Extrusion.Create(
                    pl.ToPolylineCurve(),
                    Rhino.Geometry.Plane.WorldXY,
                    jcomp['materialthickness'],
                    True)
        return cxt

    def ComponentMesh(self, jcomp: dict) -> Rhino.Geometry.Mesh:
        mesh = Rhino.Geometry.Mesh()
        vl = jcomp['geometry']['mesh']['v']
        fl = jcomp['geometry']['mesh']['f']
        [mesh.Vertices.Add(*v) for v in vl]
        [mesh.Faces.AddFace(*f) for f in fl]
        mesh.RebuildNormals()
        mesh.UnifyNormals()
        mesh.Compact()
        return mesh

    def ComponentColor(self, jcomp: dict) -> System.Drawing.Color:
        return System.Drawing.Color.FromArgb(255, *jcomp['color'])

    def PlaneToFrameDict(self, plane: Rhino.Geometry.Plane) -> dict:
        iframe = {
            'o': [plane.OriginX, plane.OriginY, plane.OriginZ],
            'x': [plane.XAxis.X, plane.XAxis.Y, plane.XAxis.Z],
            'y': [plane.YAxis.X, plane.YAxis.Y, plane.YAxis.Z],
            'z': [plane.ZAxis.X, plane.ZAxis.Y, plane.ZAxis.Z]
        }
        return iframe

    def RunScript(self, ComponentData: str, XForm: Rhino.Geometry.Transform):
        # set up output trees and results tuple
        XComponentData = System.Collections.Generic.List[System.Object]()
        if not ComponentData:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input ComponentData failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return XComponentData
        if not XForm:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input XForm failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return XComponentData
        # load component json
        jcomp = json.loads(ComponentData)
        # process insertion frame
        try:
            # try to extract insertion frame
            iframe = jcomp['iframe']
            iplane = Rhino.Geometry.Plane(
                Rhino.Geometry.Point3d(*iframe['o']),
                Rhino.Geometry.Vector3d(*iframe['x']),
                Rhino.Geometry.Vector3d(*iframe['y']),
            )
        except KeyError:
            # if there is no respective key, create world xy plane
            iplane = Rhino.Geometry.Plane.WorldXY
        # transform the iframe using the input xform
        iplane.Transform(XForm)
        # replace iframe
        jcomp['iframe'] = self.PlaneToFrameDict(iplane)
        XComponentData = json.dumps(jcomp)
        return XComponentData
