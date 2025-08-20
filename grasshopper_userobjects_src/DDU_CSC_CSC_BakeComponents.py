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
import rhinoscriptsyntax as rs
import scriptcontext as sc

# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "CSC_BakeComponents"
ghenv.Component.NickName = "CSC_BakeComponents"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "3 Component Operations"


class BakeComponents(Grasshopper.Kernel.GH_ScriptInstance):
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

    def RunScript(self,
            Bake: bool,
            ComponentData: System.Collections.Generic.List[str]):
        # set document
        sc.doc = Rhino.RhinoDoc.ActiveDoc
        # bake toggle
        if Bake:
            for i, cd in enumerate(ComponentData):
                # create path
                ghp = Grasshopper.Kernel.Data.GH_Path(i)
                # load json component
                json_comp = json.loads(cd)
                # extract ID
                comp_id = json_comp['_id']
                # get insertion plane
                try:
                    # try to extract insertion frame
                    iframe = json_comp['iframe']
                    iplane = Rhino.Geometry.Plane(
                        Rhino.Geometry.Point3d(*iframe['o']),
                        Rhino.Geometry.Vector3d(*iframe['x']),
                        Rhino.Geometry.Vector3d(*iframe['y']),
                    )
                except KeyError:
                    # if there is no respective key, create world xy plane
                    iplane = Rhino.Geometry.Plane.WorldXY
                xform = Rhino.Geometry.Transform.PlaneToPlane(
                    Rhino.Geometry.Plane.WorldXY,
                    iplane)
                # create tag
                tag = Rhino.Geometry.TextEntity()
                tag.Text = comp_id
                tag.Plane = iplane
                # specify height in millimeters
                usf = Rhino.RhinoMath.UnitScale(
                    Rhino.UnitSystem.Millimeters,
                    sc.doc.ModelUnitSystem)
                tag.TextHeight = 10.0 * usf
                tag.Justification = Rhino.Geometry.TextJustification.MiddleCenter
                id_tag = sc.doc.Objects.Add(tag)
                geo_ids = [id_tag]
                # create component geometry
                for key in sorted(json_comp['geometry'].keys()):
                    if key == 'extrusion':
                        pl = self.ComponentExtrusionProfile(json_comp)
                        xtr = self.ComponentExtrusion(json_comp)
                        pl.Transform(xform)
                        xtr.Transform(xform)
                        geo_ids.append(
                            sc.doc.Objects.Add(pl.ToPolylineCurve()))
                        geo_ids.append(sc.doc.Objects.Add(xtr))
                    elif key == 'mesh':
                        mesh = self.ComponentMesh(json_comp)
                        # transform to iframe
                        mesh.Transform(xform)
                        geo_ids.append(sc.doc.Objects.Add(mesh))
                    elif key == 'polyline':
                        pl = self.ComponentExtrusionProfile(json_comp)
                        # transform to iframe
                        pl.Transform(xform)
                        geo_ids.append(
                            sc.doc.Objects.Add(pl.ToPolylineCurve()))
                    else:
                        raise RuntimeError('Missing implementation '
                                           f'for geometry of type "{key}"!')
                # add objects to document
                # create layers if they are not present
                lay_parent = 'CSC_COMPONENTS'
                lay_name = comp_id
                layer = '::'.join([lay_parent, lay_name])
                if not rs.IsLayer(lay_parent):
                    rs.AddLayer(lay_parent)
                if not rs.IsLayer(layer):
                    rs.AddLayer(layer, self.ComponentColor(json_comp))
                # set layer to objects
                for gid in geo_ids:
                    rs.ObjectLayer(gid, layer)
                # set user data
                rs.SetUserText(
                    id_tag,
                    'componentdata',
                    ComponentData[i])
                # create group
                grp = sc.doc.Groups.Add(
                    comp_id,
                    geo_ids)
        sc.doc = ghdoc
