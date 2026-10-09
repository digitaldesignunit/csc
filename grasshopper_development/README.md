# Grasshopper Development

## Copy-Paste Info for Grasshopper Development

### Python virtual environments (Rhino 8, CPython 3.9)

The scripts run in two environments (decision 8.95). Versions are pinned in
one place, `grasshopper_lib/envs.json`; `invoke gh-headers` writes the
`# venv:` and `# r:` header of every component listed there, so do not type
them by hand. One Rhino session runs one interpreter, so `numpy` is the same
version in both.

| environment | packages | components |
|---|---|---|
| `DDU_CSC` (the bridge) | `requests`, `numpy` | Session, Fetch*, Filter*, Disassemble, Create*, Add*, builders, ReinforcementLayout, AddEvidence, ... |
| `DDU_CSC_MATCH` (matchmaking, frames) | `numpy`, `scipy`, `scikit-learn`, `trimesh`, `networkx` | ApplyFrame, ComputeFrame, ComputePCA, ComputeTSNE, ComputePCAOrientation, AssignmentPoints, RadialSignature, VisualizeEmbedding |

What a header looks like (written for you):

```
# -*- coding: utf-8 -*-
#! python3
# venv: DDU_CSC
# r: requests==2.32.5
# r: numpy==2.0.2
print('ENV OK!')
```

`trimesh` stops at 4.12.2 and `scipy` at 1.13.1 here because Rhino 8 is
Python 3.9 (the server runs trimesh 5.1 on Python 3.13; `bounds.py` is the same
code). `tests/grasshopper/test_frame_parity.py` keeps the frame of
`ComputeFrame` / `ApplyFrame` equal to the server's.

### The shared library `csc_gh` (part C, decision 8.111)

The code the components share lives in the package `grasshopper_lib/csc_gh/`
(modules `ply`, `build`, `read`, `convention`, `frame`, `upload`, `rhino`,
`doc`, `ports`, `messages`; `csc_gh.__version__`). It is installed to Rhino's
scripts folder, which Rhino 8 puts on `sys.path` of every Python 3 script, so
a component does `import csc_gh` (and `from csc_gh.build import ...`) instead
of carrying a copy. Users get it with `CSC_Update`; **you** link the folder to
the repository once, so that an edit is live in Rhino:

```
cmd /c mklink /J "%APPDATA%\McNeel\Rhinoceros\8.0\scripts\csc_gh" "<repo>\grasshopper_lib\csc_gh"
```

(a directory junction needs no administrator rights; remove a copy of the
folder first). Rhino caches imported modules: after an edit either restart
Rhino or start it with the environment variable `CSC_DEV_RELOAD=1`; then every
solve of a CSC component reloads the `csc_gh` modules in dependency order
(`importlib.reload`) and re-binds the names the component took. The tests
import the package from the repository (`tests/grasshopper/conftest.py`).

A component takes its library with a version check and shows one message when
the library is missing or too old ("CSC library <x> too old or missing: run
CSC_Update, then restart Rhino"). The declared outputs (`OUTPUTS`) and the
runtime message levels are set by `csc_gh.ports` and `csc_gh.messages`; both
imports sit in a guard, so a component never stops because of them.

Keep the `Version: <number>` line of a component the first line that matches
"version" in the file (a test checks it: the updater reads the first one), and
raise it when the source changes. `invoke gh-headers` writes the environment
header of the components `envs.json` lists (`--check` only reports); every
bridge component lists `charset_normalizer`, unpinned: an environment without
it often does not resolve and hangs.

Tests outside Rhino: `pytest tests/grasshopper` (the pure parts, in the server
environment and in a Python 3.9 environment with the pins above). The Rhino
parts run in a headless Rhino 8 with `CSC_TEST_RHINO=1` and `rhinoinside`
(a scratch virtual environment of Python 3.9, never a user environment).

### Author & Version

```
"""
Author: <Your Name>
License: MIT License
Version: 250820
"""
```

### Component Params (Python)
```
# GHENV COMPONENT SETTINGS
ghenv.Component.Name = 'Session'
ghenv.Component.NickName = 'CSC_Session'
ghenv.Component.Category = 'DDU_CSC'
ghenv.Component.SubCategory = '1 User'
ghenv.Component.Description = (
    'Component Description'
)
```

### Component SubCategories (Python)

```
ghenv.Component.SubCategory = '0 Development'
ghenv.Component.SubCategory = '1 User'
ghenv.Component.SubCategory = '2 Catalog Interface'
ghenv.Component.SubCategory = '3 Component Operations'
ghenv.Component.SubCategory = '4 RhinoDoc Interaction'
ghenv.Component.SubCategory = '5 Matchamking Tools'
ghenv.Component.SubCategory = '6 Data Tools'
ghenv.Component.SubCategory = '7 Geometry Tools'
ghenv.Component.SubCategory = '8 Visualization'
ghenv.Component.SubCategory = '9 Admin Actions'
```


### Component Params (C#)
```
// GHENV COMPONENT SETTINGS
this.Component.Name = "FindLargestFlatSide";
this.Component.NickName = "FindLargestFlatSide";
this.Component.Category = "DDU_CSC";
this.Component.SubCategory = "7 Geometry Tools";
this.Component.Description = (
    "Finds the largest flat side of a mesh using optimized algorithm. " +
    "Uses normal clustering and early termination heuristics for performance.");
```