"""The script components and the package ``csc_gh`` (invoke gh-headers).

A component is one file for Rhino 8 (CPython 3.9): these tests keep its
environment header in step with ``envs.json`` and every file, the components
and the modules of the library, to what Python 3.9, the updater and the
ASCII rule accept.
"""

from __future__ import annotations

import ast
import re

import pytest

import headers

PACKAGE = headers.LIB_DIR / 'csc_gh'
LIBS = sorted(p.stem for p in PACKAGE.glob('*.py'))
DIST = {'sklearn': 'scikit-learn', 'd2p_core': 'd2p-core-py'}
THIRD_PARTY = {'numpy', 'scipy', 'trimesh', 'requests', 'sklearn',
               'networkx', 'd2p_core'}


def _components():
    return headers.component_files()


def test_headers_are_current():
    assert headers.check() == [], 'run: invoke gh-headers'


@pytest.mark.parametrize('name', LIBS)
def test_a_library_module_is_plain_ascii_python_3_9(name):
    source = (PACKAGE / (name + '.py')).read_text(encoding='utf-8')
    source.encode('ascii')
    tree = ast.parse(source, feature_version=(3, 9))
    for node in ast.walk(tree):
        # no X | Y inside an annotation (evaluated at run time on 3.9)
        if isinstance(node, (ast.arg, ast.AnnAssign)):
            annotation = node.annotation
            if annotation is not None:
                assert not any(isinstance(n, ast.BinOp)
                               and isinstance(n.op, ast.BitOr)
                               for n in ast.walk(annotation)), name
        if isinstance(node, ast.FunctionDef):
            if node.returns is not None:
                assert not any(isinstance(n, ast.BinOp)
                               and isinstance(n.op, ast.BitOr)
                               for n in ast.walk(node.returns)), name


def test_the_package_holds_no_embedding_leftovers():
    for path in PACKAGE.glob('*.py'):
        text = path.read_text(encoding='utf-8')
        assert 'BEGIN EMBEDDED' not in text and 'gh-embed' not in text, path


@pytest.mark.parametrize('path', _components(), ids=lambda p: p.stem)
def test_a_component_is_ascii_python_3_9(path):
    source = path.read_text(encoding='utf-8')
    source.encode('ascii')
    ast.parse(source, feature_version=(3, 9))


def _imports(source):
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            found.add((node.module or '').split('.')[0])
    return found


def test_envs_json_is_consistent():
    table = headers.envs()
    assert table['envs']['DDU_CSC']['numpy'] == \
        table['envs']['DDU_CSC_MATCH']['numpy']
    names = {p.stem[len('DDU_CSC_'):] for p in _components()}
    for name, spec in table['components'].items():
        assert name in names, '%s is not a component' % name
        pins = dict(table['extras'])
        pins.update(table['envs'][spec['env']])
        for need in spec['needs']:
            assert need in pins, '%s needs unpinned %s' % (name, need)


PACKAGE_DIR = headers.LIB_DIR / 'csc_gh'


def _library_imports(source, seen=None):
    """What the ``csc_gh`` modules a source imports themselves import
    (the library runs in the environment of the component)."""
    seen = set() if seen is None else seen
    found = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0 and (node.module or '').startswith('csc_gh.'):
            module = node.module.split('.')[1]
        elif node.level == 1 and node.module:
            module = node.module.split('.')[0]
        else:
            continue
        if module in seen or not (PACKAGE_DIR / (module + '.py')).exists():
            continue
        seen.add(module)
        text = (PACKAGE_DIR / (module + '.py')).read_text(encoding='utf-8')
        found |= _imports(text) | _library_imports(text, seen)
    return found


@pytest.mark.parametrize('path', _components(), ids=lambda p: p.stem)
def test_a_component_declares_what_it_imports(path):
    name = path.stem[len('DDU_CSC_'):]
    table = headers.envs()['components']
    if name not in table:
        pytest.skip('header not managed by envs.json')
    source = path.read_text(encoding='utf-8')
    wanted = (_imports(source) | _library_imports(source)) & THIRD_PARTY
    declared = {DIST.get(n, n): n for n in table[name]['needs']}
    for module in wanted:
        assert DIST.get(module, module) in declared, (
            '%s imports %s but its header does not install it' % (name,
                                                                  module))
    # nothing over-declared except what an imported package itself needs
    implied = {'charset_normalizer'}         # an environment without it hangs
    if 'trimesh' in wanted:
        implied.add('networkx')      # a degenerate hull goes through it
    if 'sklearn' in wanted:
        implied.add('scipy')
    for dist in declared:
        assert (dist in {DIST.get(m, m) for m in wanted} or dist in implied
                ), '%s declares %s but does not import it' % (name, dist)


def test_the_environments_are_split():
    """The bridge holds requests and numpy only; the matchmaking and frame
    components are in DDU_CSC_MATCH."""
    table = headers.envs()
    assert set(table['envs']['DDU_CSC']) == {'requests', 'numpy'}
    for name in ('ApplyFrame', 'ComputeFrame', 'ComputePCA', 'ComputeTSNE',
                 'AssignmentPoints', 'ComputePCAOrientation',
                 'RadialSignature', 'VisualizeEmbedding'):
        assert table['components'][name]['env'] == 'DDU_CSC_MATCH', name
    for name in ('Session', 'CreateComponentIdentity', 'AddComponentIdentity',
                 'DisassembleComponent', 'FetchReducedGeometry'):
        assert table['components'][name]['env'] == 'DDU_CSC', name
    # the bridge environment also takes d2p-core-py (the D2P components)
    for spec in table['components'].values():
        if spec['env'] == 'DDU_CSC':
            assert set(spec['needs']) <= {'requests', 'numpy', 'd2p-core-py',
                                          'charset_normalizer'}
    for name in ('PassportToD2P', 'ReadFromD2P'):
        assert table['components'][name]['env'] == 'DDU_CSC', name


def test_the_updater_reads_the_components_own_version():
    for path in _components():
        text = path.read_text(encoding='utf-8')
        assert headers.check_version_line(text, path.name) == [], path.name


def test_the_session_names_the_0_6_client():
    text = (headers.SRC_DIR / 'DDU_CSC_Session.py').read_text(encoding='utf-8')
    assert re.search(r"^CSC_CLIENT = 'gh-userobjects/0\.6\.0\.0'$", text,
                     re.M)
    assert re.search(r'^Version: \d+(\.\d+)?[a-z]?$', text, re.M)


def test_no_component_is_left_from_0_5():
    names = {p.stem[len('DDU_CSC_'):] for p in _components()}
    assert not names & {'CreateDesign', 'AddDesign', 'FetchDesign',
                        'ApplyPCAFrame', 'CreateReinforcement',
                        'FetchDetailedGeometry'}
    assert {'Actor', 'Origin', 'IdentityMetadata', 'SnapshotMetadata',
            'Capture', 'AddEvidence', 'ReinforcementLayout', 'ApplyFrame',
            'ComputeFrame', 'FetchOriginalGeometry'} <= names
    assert {'ReadFromD2P'} <= names
    for path in _components():
        text = path.read_text(encoding='utf-8')
        for old in ("'iframe'", "'pca_frame'", "'bbx_origin'",
                    "'componenttype'"):
            assert old not in text, (path.name, old)


def test_the_invoke_tasks_file_parses_and_names_the_gh_tasks():
    source = (headers.REPO_DIR / 'tasks.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert {'gh_headers', 'gh_frame_fixtures'} <= names


def _run_script(path):
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.FunctionDef) and node.name == 'RunScript':
            return node
    return None


@pytest.mark.parametrize('path', _components(), ids=lambda p: p.stem)
def test_no_run_script_parameter_has_a_default_value(path):
    """Grasshopper does not support default values in the RunScript
    signature (decision 8.100 e): an empty input is normalised in the body
    (``if not X: X = None``)."""
    node = _run_script(path)
    if node is None:
        pytest.skip('no RunScript')
    names = [a.arg for a in node.args.args]
    assert not node.args.defaults, (
        '%s: RunScript has defaults for %s' % (
            path.name, names[len(names) - len(node.args.defaults):]))
    assert all(d is None for d in node.args.kw_defaults), path.name


RETIRED_PORTS = ('ComponentData', 'FilteredComponentData', 'XComponentData',
                 'WithPassport', 'SnapshotData', 'AddedComponentData',
                 'ComponentID', 'EvidenceData', 'ParentComponent',
                 'PrimitiveGeometry')


@pytest.mark.parametrize('path', _components(), ids=lambda p: p.stem)
def test_no_component_names_a_port_by_its_retired_name(path):
    """Glossary vocabulary (decision 8.100): component passport, request,
    identity, proxies. A retired port name in the code, a description or a
    message means a rename was missed."""
    text = path.read_text(encoding='utf-8')
    for name in RETIRED_PORTS:
        assert not re.search(r'\b%s\b' % name, text), (path.name, name)


@pytest.mark.parametrize('name', LIBS)
def test_the_library_names_no_port_by_its_retired_name(name):
    """A label in a message of the library is the name of the port the user
    sees (8.100 g): the retired names are gone from it too."""
    text = (PACKAGE / (name + '.py')).read_text(encoding='utf-8')
    for retired in RETIRED_PORTS:
        assert not re.search(r'\b%s\b' % retired, text), (name, retired)


def test_every_listed_component_lists_charset_normalizer():
    """Both environments: an environment without it often does not resolve
    and hangs (the user, 2026-10-05); it is unpinned."""
    table = headers.envs()
    assert table['extras']['charset_normalizer'] == ''
    for name, spec in table['components'].items():
        assert spec['needs'][0] == 'charset_normalizer', name
        text = (headers.SRC_DIR / ('DDU_CSC_%s.py' % name)).read_text(
            encoding='utf-8')
        assert re.search(r'^# r: charset_normalizer$', text, re.M), name
    assert 'ViewCaptureToFile' in table['components']
