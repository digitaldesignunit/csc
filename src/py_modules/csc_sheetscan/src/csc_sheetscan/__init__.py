# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

from __future__ import (absolute_import, division, print_function)
import os
import sys


# ENVIRONMENT VARIABLE SETTINGS -----------------------------------------------

# set duplicate lib env var if on osx
if sys.platform == 'darwin':
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'


# PACKAGE MODULE IMPORTS ------------------------------------------------------

from .__version__ import (__author__, __author_email__, __copyright__,
                          __description__, __license__, __title__, __url__,
                          __version__)

import csc_sheetscan.utilities as utilities # NOQA402
import csc_sheetscan.sheets as sheets # NOQA402
import csc_sheetscan.label as label # NOQA402


# DEFINITIONS -----------------------------------------------------------------

ROOTDIR = os.path.dirname(__file__)
"""str: Path to the root folder of the package."""

REPODIR = utilities.sanitize_path(os.path.join(ROOTDIR, "../.."))
"""str: Path to the root folder of the repository."""

DATADIR = utilities.sanitize_path(os.path.join(ROOTDIR, "../../data"))
"""str: Path to the data folder of the repository."""

TESTDIR = utilities.sanitize_path(os.path.join(ROOTDIR, "../../tests"))
"""str: Path to the tests folder of the repository."""

IMGDIR = utilities.sanitize_path(os.path.join(ROOTDIR, "sheets"))
"""str: Path to the sheets folder of the repository."""

_STICKY = {}
"""dict: Sticky dictionary for storing of persistent data."""

__all__ = [
    "__author__", "__author_email__", "__copyright__", "__description__",
    "__license__", "__title__", "__url__", "__version__",
]
