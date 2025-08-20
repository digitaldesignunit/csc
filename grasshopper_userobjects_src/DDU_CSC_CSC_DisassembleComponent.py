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
ghenv.Component.Name = "CSC_DisassembleComponent"
ghenv.Component.NickName = "CSC_DisassembleComponent"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "3 Component Operations"


class DisassembleComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250820
    """

    def ComponentExtrusionProfile(
            self,
            json_comp: dict) -> Rhino.Geometry.Polyline:
        pl = Rhino.Geometry.Polyline()
        pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
               for pt in json_comp['geometry']['extrusion']['profile']]
        pl.AddRange(pts)
        return pl

    def ComponentExtrusion(
            self,
            json_comp: dict) -> Rhino.Geometry.Extrusion:
        pl = Rhino.Geometry.Polyline()
        pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
               for pt in json_comp['geometry']['extrusion']['profile']]
        pl.AddRange(pts)
        cxt = Rhino.Geometry.Extrusion.Create(
            pl.ToPolylineCurve(),
            Rhino.Geometry.Plane.WorldXY,
            json_comp['geometry']['extrusion']['height'],
            True)
        # move extrusion downwards half material
        # thickness to center it at the origin
        cxt.Translate(Rhino.Geometry.Vector3d(
            0, 0, json_comp['geometry']['extrusion']['height'] * -0.5))
        return cxt

    def ComponentMesh(self, json_comp: dict) -> Rhino.Geometry.Mesh:
        mesh = Rhino.Geometry.Mesh()
        vl = json_comp['geometry']['mesh']['v']
        fl = json_comp['geometry']['mesh']['f']
        [mesh.Vertices.Add(*v) for v in vl]
        [mesh.Faces.AddFace(*f) for f in fl]
        try:
            cl = json_comp['geometry']['mesh']['c']
            [mesh.VertexColors.Add(
                System.Drawing.Color.FromArgb(*c)) for c in cl]
        except KeyError:
            print('Mesh contains no colors...')
        mesh.RebuildNormals()
        mesh.UnifyNormals()
        mesh.Compact()
        return mesh

    def ComponentColor(self, json_comp: dict) -> System.Drawing.Color:
        return System.Drawing.Color.FromArgb(255, *json_comp['color'])

    def ComponentBoundingBox(
            self,
            json_comp: dict) -> Rhino.Geometry.BoundingBox:
        minpt = json_comp['bbx'][0]
        maxpt = json_comp['bbx'][1]
        bbx = Rhino.Geometry.BoundingBox(
            Rhino.Geometry.Point3d(*minpt),
            Rhino.Geometry.Point3d(*maxpt))
        return bbx

    def RunScript(self, ComponentData: Grasshopper.DataTree[str]):
        # set up output trees and results tuple
        ID = Grasshopper.DataTree[System.Object]()
        Type = Grasshopper.DataTree[System.Object]()
        Material = Grasshopper.DataTree[System.Object]()
        Geometry = Grasshopper.DataTree[System.Object]()
        Color = Grasshopper.DataTree[System.Object]()
        BoundingBox = Grasshopper.DataTree[System.Object]()
        __Results = (
            ID,
            Type,
            Material,
            Geometry,
            Color,
            BoundingBox)
        # loop over all branches
        for i in range(ComponentData.BranchCount):
            for j, comp in enumerate(ComponentData.Branches[i]):
                json_comp = json.loads(comp)
                # create datatree path
                ghp = ComponentData.Paths[i]
                # add directly available metadata to the
                # respective datatrees
                ID.Add(json_comp['_id'], ghp)
                Type.Add(json_comp['type'], ghp)
                Material.Add(json_comp['material'], ghp)
                # process insertion frame
                try:
                    iframe = json_comp['iframe']
                    iplane = Rhino.Geometry.Plane(
                        Rhino.Geometry.Point3d(*iframe['o']),
                        Rhino.Geometry.Vector3d(*iframe['x']),
                        Rhino.Geometry.Vector3d(*iframe['y']),
                    )
                except KeyError:
                    iplane = Rhino.Geometry.Plane.WorldXY
                xform = Rhino.Geometry.Transform.PlaneToPlane(
                    Rhino.Geometry.Plane.WorldXY,
                    iplane)
                # treat geometry key in a special way because
                # it may hold mutiple geometry types
                for key in sorted(json_comp['geometry'].keys()):
                    if key == 'extrusion':
                        pl = self.ComponentExtrusionProfile(json_comp)
                        xtr = self.ComponentExtrusion(json_comp)
                        # transform to iframe
                        pl.Transform(xform)
                        xtr.Transform(xform)
                        # add to datatree
                        Geometry.Add(pl, ghp)
                        Geometry.Add(xtr, ghp)
                    elif key == 'mesh':
                        mesh = self.ComponentMesh(json_comp)
                        # transform to iframe
                        mesh.Transform(xform)
                        # add to datatree
                        Geometry.Add(mesh, ghp)
                    elif key == 'polyline':
                        pl = self.ComponentExtrusionProfile(json_comp)
                        # transform to iframe
                        pl.Transform(xform)
                        # add to datatree
                        Geometry.Add(pl, ghp)
                    else:
                        raise RuntimeError('Missing implementation '
                                           f'for geometry of type "{key}"!')
                # create system color from rgb values
                color = self.ComponentColor(json_comp)
                Color.Add(color, ghp)
                # construct boundingbox
                bbx = self.ComponentBoundingBox(json_comp)
                # apply iframe transform
                bbx.Transform(xform)
                BoundingBox.Add(bbx, ghp)
        # return output trees
        return __Results
