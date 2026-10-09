#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os  # NOQA
import datetime  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ViewCaptureToFile'  # NOQA
ghenv.Component.NickName = 'ViewCaptureToFile'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '8 Visualization'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Captures the active Rhino viewport to an image file (PNG). Supports '
    'custom dimensions, background colors, and visibility options for '
    'grid/axes. Creates organized capture folders with timestamps.'
)

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('Path', 'Path',
     'Path to the captured image file'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_ViewCaptureToFile(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Anders Holden Deleuran (updated 2025 by Max Benjamin Eschenbach)
    License: MIT License
    Version: 261005
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def checkOrMakeFolder(self):
        """
        Check/makes a "Captures" folder in the GH def folder and a subfolder
        in the format 'YYMMDD'.
        """
        # get ghdoc
        ghdoc = self.Component.OnPingDocument()
        # construct timestamp for subfolder
        date = datetime.date.today()
        yy = str(date.year)[-2:]
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)
        timestamp = yy + mm + dd
        docpath = ghdoc.Path  # NOQA
        if docpath:
            folder = os.path.dirname(docpath)
            captureFolder = folder + "\\Captures\\" + timestamp
            if not os.path.isdir(captureFolder):
                os.makedirs(captureFolder)
            return captureFolder

    def makeFileName(self):
        """ Make a string with the gh def name + current hourMinuteSecond """
        # Make hour minute seconds string
        n = datetime.datetime.now()
        ho, mt, sc = str(n.hour), str(n.minute), str(n.second)
        if len(ho) == 1:
            ho = "0" + ho
        if len(mt) == 1:
            mt = "0" + mt
        if len(sc) == 1:
            sc = "0" + sc
        hms = ho + mt + sc
        # Get name of GH def
        ghDef = ghdoc.Name.strip("*")  # NOQA
        # Concatenate and return
        fileName = ghDef + "_" + hms
        return fileName

    def captureActiveViewToFile(
            self,
            width,
            height,
            path,
            grid,
            worldAxes,
            cplaneAxes):
        """
        Captures the active view to an image file at the path.
        Path looks like this:
        "C:\\Users\\user\\Desktop\\Captures\\foo_bar.png"
        """
        # Set the script context to the current Rhino doc
        sc.doc = Rhino.RhinoDoc.ActiveDoc
        # define ghdoc
        ghdoc = self.Component.OnPingDocument()
        # Get the active view and set image dimensions
        activeView = sc.doc.Views.ActiveView
        # Perform the capture
        try:
            viewcap = Rhino.Display.ViewCapture()
            viewcap.DrawGrid = grid
            viewcap.DrawGridAxes = worldAxes
            viewcap.DrawAxes = cplaneAxes
            viewcap.Height = height
            viewcap.Width = width
            imageCap = viewcap.CaptureToBitmap(activeView)
            System.Drawing.Bitmap.Save(imageCap, path)
            Rhino.RhinoApp.WriteLine(path)
            sc.doc = ghdoc  # NOQA
            return path
        except Exception as e:
            sc.doc = ghdoc  # NOQA
            raise Exception(f'Capture failed, check the path: {str(e)}')

    def _state(self, text=''):
        """The one short state under the component (decision 8.113)."""
        if set_state is not None:
            set_state(self.Component, text)

    def _stop(self):
        """True when RunScript has to return early: the outputs were just
        updated (says why)."""
        if self._outputs_note:
            self._addRemark(self._outputs_note)
        return not self._outputs_ready

    def _check_outputs(self):
        """Make the outputs match OUTPUTS before the script runs (8.112)."""
        self._outputs_ready, self._outputs_note = True, None
        if ensure_outputs is None:
            self._outputs_note = (
                'output check skipped: CSC library not installed')
            return
        status = ensure_outputs(self.Component, OUTPUTS)
        self._outputs_ready, self._outputs_note = status.ready, status.remark

    def BeforeRunScript(self):
        """Perform some setup actions."""
        self._check_outputs()

    def RunScript(self,
            Toggle: bool,
            Width: int,
            Height: int,
            BackgroundColor: System.Drawing.Color,
            Grid: bool,
            WorldAxes: bool,
            CPlaneAxes: bool,
            OpenFile: bool):
        """
        Main execution method for capturing the active view to a file.

        Args:
            Toggle: Boolean to execute the capture operation
            Width: Image width in pixels (default: 1920)
            Height: Image height in pixels (default: 1080)
            BackgroundColor: Background color for the viewport
            Grid: Show grid in capture
            WorldAxes: Show world axes in capture
            CPlaneAxes: Show construction plane axes in capture
            OpenFile: Open the captured file after creation

        Returns:
            Path to the captured image file
        """
        if self._stop():
            return empty_outputs()
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'Toggle to execute the view capture operation'
        )
        self.InputParams[1].Description = (
            'Image width in pixels (default: 1920 if not provided)'
        )
        self.InputParams[2].Description = (
            'Image height in pixels (default: 1080 if not provided)'
        )
        self.InputParams[3].Description = (
            'Background color for the viewport capture'
        )
        self.InputParams[4].Description = (
            'Show grid in the captured image'
        )
        self.InputParams[5].Description = (
            'Show world axes in the captured image'
        )
        self.InputParams[6].Description = (
            'Show construction plane axes in the captured image'
        )
        self.InputParams[7].Description = (
            'Open the captured file after creation'
        )

        # Set up output trees and results
        Path = Grasshopper.DataTree[System.Object]()

        if not Toggle:
            self._state('Toggle is off')
            return Path

        try:
            # Set background color if provided
            if BackgroundColor:
                settings = Rhino.ApplicationSettings.AppearanceSettings
                settings.ViewportBackgroundColor = BackgroundColor
                self._addRemark('Background color set for capture')

            # Set default dimensions if not provided
            if not Width:
                Width = 1920
            if not Height:
                Height = 1080


            # Create capture folder and filename
            capFolder = self.checkOrMakeFolder()
            fileName = self.makeFileName()
            path = os.path.join(capFolder, fileName + '.png')


            # Perform the capture
            captured_path = self.captureActiveViewToFile(
                Width, Height, path, Grid, WorldAxes, CPlaneAxes
            )

            # Add to output
            ghp = Grasshopper.Kernel.Data.GH_Path(0)
            Path.Add(captured_path, ghp)

            # Open file if requested
            if OpenFile:
                os.startfile(path)
                self._addRemark('File opened after capture')

            self._state(f'Captured {fileName}.png')
            self._addRemark(f'Successfully captured view to {captured_path}')

            return Path

        except Exception as e:
            msg = f'Capture failed: {str(e)}'
            self._addError(msg)
            return Path
