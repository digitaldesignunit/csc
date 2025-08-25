#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import concurrent.futures
from typing import Dict, Tuple, Any

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'DisassembleComponentParallel'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'DisassembleComponentParallel'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_DisassembleComponentParallel(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach (Parallelized Version)
    License: MIT License
    Version: 250822-Parallel
    Description: Parallelized version of DisassembleComponent for 
                improved performance
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
        # Try to get mesh-specific colors first
        try:
            cl = json_comp['geometry']['mesh']['c']
            [mesh.VertexColors.Add(
                System.Drawing.Color.FromArgb(*c)) for c in cl]
        except KeyError:
            # Fallback: use component color for all vertices
            try:
                component_color = System.Drawing.Color.FromArgb(
                    255, *json_comp['color'])
                for _ in range(len(vl)):
                    mesh.VertexColors.Add(component_color)
            except (KeyError, TypeError):
                # If even component color fails, use a default gray
                default_color = System.Drawing.Color.Gray
                for _ in range(len(vl)):
                    mesh.VertexColors.Add(default_color)
                self._addWarning(
                    f'Mesh {json_comp["_id"]} using default gray color')
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

    def process_single_component(self, comp_data: Tuple[str, int, int]) -> Dict[str, Any]:
        """
        Process a single component and return its processed data.
        This method is designed to be called in parallel.
        
        Args:
            comp_data: Tuple of (component_json_string, branch_index, 
                       component_index)
            
        Returns:
            Dictionary containing all processed component data
        """
        comp, branch_idx, comp_idx = comp_data
        
        try:
            json_comp = json.loads(comp)
            
            # Process insertion frame
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

            # Process geometry
            geometry_objects = []
            for key in sorted(json_comp['geometry'].keys()):
                if key == 'extrusion':
                    pl = self.ComponentExtrusionProfile(json_comp)
                    xtr = self.ComponentExtrusion(json_comp)
                    # transform to iframe
                    pl.Transform(xform)
                    xtr.Transform(xform)
                    geometry_objects.extend([pl, xtr])
                elif key == 'mesh':
                    mesh = self.ComponentMesh(json_comp)
                    # transform to iframe
                    mesh.Transform(xform)
                    geometry_objects.append(mesh)
                elif key == 'polyline':
                    pl = self.ComponentExtrusionProfile(json_comp)
                    # transform to iframe
                    pl.Transform(xform)
                    geometry_objects.append(pl)

            # Process color
            color = self.ComponentColor(json_comp)

            # Process bounding box
            bbx = self.ComponentBoundingBox(json_comp)
            bbx.Transform(xform)

            # Process descriptors
            try:
                descriptors = json_comp.get('descriptors', {})
                descriptors_json = json.dumps(descriptors)
            except KeyError:
                descriptors_json = json.dumps({})

            return {
                'success': True,
                'branch_idx': branch_idx,
                'comp_idx': comp_idx,
                'id': json_comp['_id'],
                'type': json_comp['type'],
                'material': json_comp['material'],
                'geometry': geometry_objects,
                'color': color,
                'bounding_box': bbx,
                'descriptors': descriptors_json,
                'error': None
            }

        except json.JSONDecodeError as e:
            return {
                'success': False,
                'branch_idx': branch_idx,
                'comp_idx': comp_idx,
                'error': f'Failed to parse component data: {str(e)}',
                'id': None,
                'type': None,
                'material': None,
                'geometry': [],
                'color': None,
                'bounding_box': None,
                'descriptors': None
            }
        except Exception as e:
            return {
                'success': False,
                'branch_idx': branch_idx,
                'comp_idx': comp_idx,
                'error': f'Error processing component: {str(e)}',
                'id': None,
                'type': None,
                'material': None,
                'geometry': [],
                'color': None,
                'bounding_box': None,
                'descriptors': None
            }

    def RunScript(self, ComponentData: Grasshopper.DataTree[str]):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'The ComponentData that was fetched from the server as JSON.')

        # Initialize output param descriptions
        self.OutputParams[0].Description = 'Component ID (GUID)'
        self.OutputParams[1].Description = (
            'Component type (sheet, beam, slab, etc.)'
        )
        self.OutputParams[2].Description = 'Component material'
        self.OutputParams[3].Description = (
            'Rhino geometry objects (extrusion, mesh, polyline)'
        )
        self.OutputParams[4].Description = (
            'Component color as System.Drawing.Color'
        )
        self.OutputParams[5].Description = (
            'Component bounding box as Rhino.Geometry.BoundingBox'
        )
        self.OutputParams[6].Description = (
            'Component descriptors/metadata as JSON string'
        )

        try:
            # set up output trees and results tuple
            ID = Grasshopper.DataTree[System.Object]()
            Type = Grasshopper.DataTree[System.Object]()
            Material = Grasshopper.DataTree[System.Object]()
            Geometry = Grasshopper.DataTree[System.Object]()
            Color = Grasshopper.DataTree[System.Object]()
            BoundingBox = Grasshopper.DataTree[System.Object]()
            Descriptors = Grasshopper.DataTree[System.Object]()
            __Results = (
                ID,
                Type,
                Material,
                Geometry,
                Color,
                BoundingBox,
                Descriptors)

            # Validate input
            if not ComponentData or ComponentData.DataCount == 0:
                msg = ('No component data provided. Please connect '
                       'FetchComponent output.')
                self._addWarning(msg)
                self.Component.Message = msg
                return __Results

            self.Component.Message = 'Disassembling components in parallel...'

            # Prepare data for parallel processing
            components_to_process = []
            for i in range(ComponentData.BranchCount):
                for j, comp in enumerate(ComponentData.Branches[i]):
                    components_to_process.append((comp, i, j))

            # Determine optimal number of workers
            # Use min of available CPU cores or component count, but cap at 8 
            # to avoid overwhelming the system
            import os
            max_workers = min(
                min(os.cpu_count() or 4, len(components_to_process)),
                8
            )

            self._addRemark(
                f'Processing {len(components_to_process)} components using '
                f'{max_workers} workers'
            )

            # Process components in parallel
            processed_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_comp = {
                    executor.submit(self.process_single_component, comp_data): comp_data
                    for comp_data in components_to_process
                }

                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_comp):
                    result = future.result()
                    processed_results.append(result)

            # Sort results by branch and component index to maintain order
            processed_results.sort(
                key=lambda x: (x['branch_idx'], x['comp_idx'])
            )

            # Add results to output trees
            for result in processed_results:
                if result['success']:
                    # Get the original path from ComponentData
                    ghp = ComponentData.Paths[
                        result['branch_idx']
                    ]
                    
                    # Add all processed data to output trees
                    ID.Add(result['id'], ghp)
                    Type.Add(result['type'], ghp)
                    Material.Add(result['material'], ghp)
                    
                    # Add geometry objects
                    for geom in result['geometry']:
                        Geometry.Add(geom, ghp)
                    
                    Color.Add(result['color'], ghp)
                    BoundingBox.Add(
                        result['bounding_box'], ghp
                    )
                    Descriptors.Add(
                        result['descriptors'], ghp
                    )
                else:
                    # Log errors for failed components
                    self._addError(result['error'])

            # Update success message
            total_components = len(components_to_process)
            successful_components = sum(1 for r in processed_results if r['success'])
            failed_components = total_components - successful_components
            
            self.Component.Message = (
                f'Disassembled {successful_components}/{total_components} component(s)'
            )
            
            if failed_components > 0:
                self._addWarning(f'{failed_components} components failed to process')
            else:
                self._addRemark(
                    f'Successfully disassembled {successful_components} components in parallel'
                )

            # return output trees
            return __Results

        except Exception as e:
            msg = f'Unexpected error during parallel disassembly: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

            # Return empty results if there was an error
            ID = Grasshopper.DataTree[System.Object]()
            Type = Grasshopper.DataTree[System.Object]()
            Material = Grasshopper.DataTree[System.Object]()
            Geometry = Grasshopper.DataTree[System.Object]()
            Color = Grasshopper.DataTree[System.Object]()
            BoundingBox = Grasshopper.DataTree[System.Object]()
            Descriptors = Grasshopper.DataTree[System.Object]()
            __Results = (
                ID,
                Type,
                Material,
                Geometry,
                Color,
                BoundingBox,
                Descriptors)
            return __Results
