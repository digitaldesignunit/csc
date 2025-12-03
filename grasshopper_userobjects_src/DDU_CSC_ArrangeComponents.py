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
import json  # NOQA
import math  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ArrangeComponents'  # NOQA
ghenv.Component.NickName = 'ArrangeComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Arranges components in an even square grid based on their bounding '
    'boxes. Calculates grid cell size from the largest component dimension.'
)


class CSC_ArrangeComponents(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Component data as JSON strings'
        )
        self.InputParams[1].Description = (
            'Additional spacing between grid cells'
        )
        self.InputParams[2].Description = (
            'Insertion point (starting corner of grid)'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Grid cell outlines as polylines'
        )
        self.OutputParams[1+i].Description = (
            'XY planes at center of each grid cell'
        )
        self.OutputParams[2+i].Description = (
            'Transformations from world origin to grid cell planes'
        )

    def extract_bounding_box_dimensions(self, component_data: str):
        """
        Extract bounding box dimensions from component JSON.

        Args:
            component_data: Component data as JSON string

        Returns:
            Tuple of (xtx, xty, xtz) dimensions or None
        """
        try:
            json_comp = json.loads(component_data)
            bbx = json_comp.get('bbx', None)
            if bbx and len(bbx) >= 3:
                return bbx[0], bbx[1], bbx[2]
            return None
        except (json.JSONDecodeError, KeyError,
                TypeError):
            return None

    def calculate_grid_size(self, count: int):
        """
        Calculate grid dimensions for a square grid.

        Returns:
            Tuple of (grid_size_x, grid_size_y, cells_needed)
        """
        grid_size = int(math.ceil(math.sqrt(count)))
        cells_needed = grid_size * grid_size
        return grid_size, grid_size, cells_needed

    def create_grid_cell_polyline(
            self, cell_size: float,
            center_point: Rhino.Geometry.Point3d):
        """
        Create a square cell polyline centered at given point.

        Args:
            cell_size: Size of the grid cell
            center_point: Center point of the cell

        Returns:
            Polyline outlining the cell
        """
        half_size = cell_size * 0.5

        # Create corners relative to center
        x_min = center_point.X - half_size
        x_max = center_point.X + half_size
        y_min = center_point.Y - half_size
        y_max = center_point.Y + half_size
        z = center_point.Z

        corners = [
            Rhino.Geometry.Point3d(x_min, y_min, z),
            Rhino.Geometry.Point3d(x_max, y_min, z),
            Rhino.Geometry.Point3d(x_max, y_max, z),
            Rhino.Geometry.Point3d(x_min, y_max, z),
            Rhino.Geometry.Point3d(x_min, y_min, z)
        ]

        return Rhino.Geometry.Polyline(corners)

    def RunScript(self,
            ComponentData: Grasshopper.DataTree[object],
            Spacing: float,
            InsertionPoint: Rhino.Geometry.Point3d):

        # Default values for optional parameters
        if Spacing is None:
            Spacing = 100.0
        if InsertionPoint is None:
            InsertionPoint = Rhino.Geometry.Point3d(0.0, 0.0, 0.0)

        # Set up output trees
        GridCells = Grasshopper.DataTree[Rhino.Geometry.Polyline]()
        GridPlanes = Grasshopper.DataTree[Rhino.Geometry.Plane]()
        XForm = Grasshopper.DataTree[Rhino.Geometry.Transform]()

        # Validate input
        if not ComponentData or ComponentData.DataCount == 0:
            msg = 'No component data provided'
            self._addWarning(msg)
            self.Component.Message = msg
            return GridCells, GridPlanes, XForm

        try:
            # Extract bounding box dimensions for all components
            all_dimensions = []
            paths = []
            for i, branch in enumerate(ComponentData.Branches):
                branch_path = ComponentData.Paths[i]
                for comp_data in branch:
                    if comp_data is None:
                        continue
                    dims = self.extract_bounding_box_dimensions(comp_data)
                    if dims:
                        all_dimensions.append(dims)
                        paths.append(branch_path)
            if not all_dimensions:
                msg = 'No valid bounding boxes in component data'
                self._addWarning(msg)
                self.Component.Message = msg
                return GridCells, GridPlanes, XForm
            # Find the largest x and y dimensions to determine grid cell size
            max_x_dim = max(dims[0] for dims in all_dimensions)
            max_y_dim = max(dims[1] for dims in all_dimensions)
            cell_size = max(max_x_dim, max_y_dim) + Spacing
            # Calculate grid layout
            comp_count = len(all_dimensions)
            grid_x, grid_y, cells_needed = self.calculate_grid_size(comp_count)
            # Adjust to fit exact number of components
            arranged_count = min(comp_count, cells_needed)
            # Create grid cells
            for i in range(arranged_count):
                # Calculate grid position (row, col)
                row = i // grid_x
                col = i % grid_x
                # Calculate center point for this cell
                center_x = InsertionPoint.X + col * cell_size + cell_size * 0.5
                center_y = InsertionPoint.Y + row * cell_size + cell_size * 0.5
                cell_center = Rhino.Geometry.Point3d(
                    center_x,
                    center_y,
                    InsertionPoint.Z
                )
                # Create grid cell outline
                grid_cell = self.create_grid_cell_polyline(
                    cell_size, cell_center)
                GridCells.Add(grid_cell, paths[i])
                # Create plane at center of grid cell
                grid_plane = Rhino.Geometry.Plane(
                    cell_center,
                    Rhino.Geometry.Vector3d.XAxis,
                    Rhino.Geometry.Vector3d.YAxis
                )
                GridPlanes.Add(grid_plane, paths[i])

                # Create transform from world origin to grid cell plane
                world_plane = Rhino.Geometry.Plane.WorldXY
                xform = Rhino.Geometry.Transform.PlaneToPlane(
                    world_plane, grid_plane)
                XForm.Add(xform, paths[i])

            # Update component message
            if arranged_count < comp_count:
                self._addWarning(
                    f'Arranged {arranged_count} of {comp_count} components')
            else:
                self._addRemark(
                    f'Arranged {arranged_count} components in '
                    f'{grid_x}x{grid_y} grid')

            return GridCells, GridPlanes, XForm

        except Exception as e:
            msg = f'Error arranging components: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
            return GridCells, GridPlanes, XForm
