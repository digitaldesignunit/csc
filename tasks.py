# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import contextlib
import getpass
import os
import sys
import uuid


# ADDITIONAL MODULE IMPORTS ---------------------------------------------------

from invoke import task, exceptions


# TASK DEFINITIONS ------------------------------------------------------------

@task(default=True)
def help(c):
    """
    Lists all available tasks and info on their usage.
    """
    c.run("invoke --list")
    print("Use \"invoke -h <taskname>\" to get detailed help for a task.")


@task()
def gource(c, mode='overview', output_dir='viz'):
    """
    Create gource video in specified output directory.

    Args:
        mode: Either 'overview' or 'track' (default: 'overview')
        output_dir: Output directory for the video (default: 'viz')
    """
    if mode not in ['overview', 'track']:
        raise ValueError("Mode must be either 'overview' or 'track'")

    repodir = os.path.normpath(os.path.dirname(__file__))
    with chdir(repodir):
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Gource visualization
        try:
            print(f"Creating gource {mode} visualization...")

            if mode == 'overview':
                gource_cmd = (
                    "gource {0} -1920x1080 -f --multi-sampling -a 1 "
                    "-s 1 --hide bloom,mouse,progress --camera-mode "
                    "overview -r 60 -o {1}/{2}.ppm"
                ).format(repodir, output_dir, mode)
                c.run(gource_cmd)
            else:  # track mode
                gource_cmd = (
                    "gource {0} -1920x1080 -f --multi-sampling -a 1 "
                    "-s 1 --hide bloom,mouse,progress --camera-mode "
                    "track -r 60 -o {1}/{2}.ppm"
                ).format(repodir, output_dir, mode)
                c.run(gource_cmd)
        except exceptions.UnexpectedExit:
            print("Gource is not installed or not in the current PATH! "
                  "See https://gource.io/ for info on installation.")
            return

        # FFmpeg conversion
        try:
            print("Converting using FFMPEG...")
            ffmpeg_cmd = (
                "ffmpeg -y -r 60 -f image2pipe -vcodec ppm -i "
                "{0}/{1}.ppm -vcodec libx264 -preset medium "
                "-pix_fmt yuv420p -crf 1 -threads 0 -bf 0 "
                "{0}/{1}.mp4"
            ).format(output_dir, mode)
            c.run(ffmpeg_cmd)
            os.remove(f"{output_dir}/{mode}.ppm")
            print(f"Video saved to {output_dir}/{mode}.mp4")
        except exceptions.UnexpectedExit:
            print("FFmpeg is not installed or not in the current PATH! "
                  "See https://ffmpeg.org/ for info on installation.")


# LOCAL DEVELOPMENT AND TESTS -------------------------------------------------
# See README, "Local development and tests". Everything below runs against a
# local MongoDB Community Server; nothing here touches production.

REPO_DIR = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(REPO_DIR, 'src', 'backend')
DEV_ENV_FILE = os.path.join(BACKEND_DIR, 'dev.env')
DUMPS_DIR = os.path.join(REPO_DIR, 'mongodb_collections_local')
_PATH_KEYS = ('_DIR', 'CLIENT_LOG_PATH')


def _read_dev_env():
    """KEY=VALUE lines of src/backend/dev.env; relative paths -> repo root."""
    if not os.path.isfile(DEV_ENV_FILE):
        sys.exit('src/backend/dev.env not found: copy dev.env.example first')
    env = {}
    with open(DEV_ENV_FILE, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key, value = key.strip(), value.strip()
            if key.endswith(_PATH_KEYS) and not os.path.isabs(value):
                value = os.path.normpath(os.path.join(REPO_DIR, value))
            env[key] = value
    return env


def _local_db(env):
    from pymongo import MongoClient
    uri = env['MONGODB_URI']
    host = uri.split('://', 1)[-1].split('/', 1)[0]
    if not host.startswith(('127.0.0.1', 'localhost')):
        sys.exit(f'refusing to touch a non-local database: {host}')
    return MongoClient(uri, serverSelectionTimeoutMS=3000)['csc']


def _pytest(c, target='tests', *, k='', parallel=True, slow=False,
            extra='', env=None):
    """One pytest run from the repository root. ``-n auto`` = pytest-xdist,
    every worker with its own throwaway mongod (decision 8.114); ``slow``
    includes the tests marked slow."""
    flags = ' -n auto' if parallel else ''
    flags += ' -m ""' if slow else ''
    flags += f' -k "{k}"' if k else ''
    with chdir(REPO_DIR):
        return c.run(f'{sys.executable} -m pytest {target}{flags}{extra}',
                     env=env or {}, pty=False, warn=True)


def _tree_hash(c):
    """The tree a run was made on: the index plus every tracked and
    untracked change, as `git write-tree` of a temporary index."""
    import tempfile
    with chdir(REPO_DIR):
        tmp = os.path.join(tempfile.gettempdir(),
                           f'csc-index-{uuid.uuid4().hex[:8]}')
        env = {'GIT_INDEX_FILE': tmp}
        try:
            c.run('git read-tree HEAD', env=env, hide=True, pty=False)
            c.run('git add -A', env=env, hide=True, pty=False)
            return c.run('git write-tree', env=env, hide=True,
                         pty=False).stdout.strip()
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


@task(help={
    'k': 'only run tests matching this expression (pytest -k)',
    'dump': 'also run the dump smoke test against mongodb_collections_local/<dump>',
    'all': 'include the tests marked slow',
    'parallel': 'pytest-xdist, one throwaway mongod per worker (default off)',
})
def test(c, k='', dump='', all=False, parallel=False):  # noqa: A002
    """
    Run the test suite (unit tests + route tests on a throwaway mongod).
    Tests marked slow are left out unless --all is given.
    """
    env = {}
    if dump:
        env['CSC_DUMP_DIR'] = os.path.join(DUMPS_DIR, dump)
    result = _pytest(c, k=k, parallel=parallel, slow=all, env=env)
    if result.failed:
        sys.exit(result.return_code)


@task(help={
    'base': 'compare the working tree with this ref instead of HEAD',
})
def test_changed(c, base='HEAD'):
    """
    Run the tests that belong to the changed paths (tier 1).

    Decision 8.114: git diff (working tree and index against HEAD or --base, plus untracked
    files) is mapped to test folders: backend api -> tests/api, other backend
    -> tests/catalog + tests/api, grasshopper -> tests/grasshopper, a changed
    test -> itself, frontend -> lint + tsc + the tests next to changed lib
    files. Nothing mapped: `pytest --lf`.
    """
    sys.path.insert(0, os.path.join(REPO_DIR, 'scripts', 'dev'))
    import changed_tests
    with chdir(REPO_DIR):
        paths = changed_tests.changed_paths(REPO_DIR, base)
        plan = changed_tests.plan(paths)
    print(f'{len(paths)} changed path(s) -> pytest: '
          f'{plan.pytest_targets or "-"}; frontend: {plan.frontend}')
    failed = False
    if plan.empty:
        failed = _pytest(c, '--lf', parallel=False).failed
    else:
        if plan.pytest_targets:
            whole_folder = any(t in ('tests/api', 'tests/catalog')
                               for t in plan.pytest_targets)
            failed = _pytest(c, ' '.join(plan.pytest_targets),
                             parallel=whole_folder).failed
        if plan.frontend:
            with chdir(os.path.join(REPO_DIR, 'src', 'frontend')):
                for command in ('npx tsc --noEmit', 'npm run lint'):
                    failed = c.run(command, pty=False, warn=True).failed                         or failed
                if plan.frontend_tests:
                    files = ' '.join(f'"{t}"' for t in plan.frontend_tests)
                    failed = c.run(f'npx tsx --test {files}', pty=False,
                                   warn=True).failed or failed
    if failed:
        sys.exit(1)


@task
def test_all(c):
    """
    Full suite without the slow tests, in parallel; prints the tree hash.

    Tier 2 (decision 8.114): pytest -n auto (one throwaway mongod per
    worker), then the tree it ran on (git write-tree) --- name it in the
    report that hands a part to the review.
    """
    tree = _tree_hash(c)
    result = _pytest(c)
    print(f'tree: {tree} (git write-tree, tracked and untracked changes)')
    if result.failed:
        sys.exit(result.return_code)


@task
def test_release(c):
    """
    Everything including the slow tests; run once before tagging.

    Tier 4 (decision 8.114): all tests including the slow ones (headless
    Rhino with CSC_TEST_RHINO=1, a migration on a dump with CSC_DUMP_DIR, fits
    on real PLYs). Run it once before tagging: CI does not run
    tests/catalog.
    """
    tree = _tree_hash(c)
    result = _pytest(c, slow=True)
    print(f'tree: {tree} (git write-tree, tracked and untracked changes)')
    if result.failed:
        sys.exit(result.return_code)


@task
def check_server_wheels(c):
    """
    Check that the backend installs on Uberspace 7 without compiling.

    Resolves requirements.txt + constraints.txt for CPython 3.13 on glibc 2.17
    (manylinux2014) with binary wheels only, as `pip install` on the server
    would, and fails if any package lacks such a wheel.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as dest, chdir(BACKEND_DIR):
        c.run(f'{sys.executable} -m pip download -q -r requirements.txt '
              f'-c constraints.txt --only-binary=:all: --python-version 3.13 '
              f'--platform manylinux2014_x86_64 '
              f'--platform manylinux_2_17_x86_64 -d "{dest}"', pty=False)
    print('ok: every backend dependency has a glibc 2.17 wheel for 3.13')


@task
def dev_backend(c):
    """
    Run the FastAPI backend locally with auto-reload (src/backend/dev.env).
    """
    env = _read_dev_env()
    for key, value in env.items():
        if key.endswith('_DIR'):
            os.makedirs(value, exist_ok=True)
    with chdir(BACKEND_DIR):
        c.run(f'{sys.executable} -m uvicorn main_fastapi:app --reload '
              f'--host 127.0.0.1 --port 8000', env=env, pty=False)


@task(help={
    'dump': 'dump folder name in mongodb_collections_local, e.g. 260916',
    'replace': 'empty each collection before loading it',
})
def seed(c, dump, replace=False):
    """
    Load a local catalog dump into the local database from dev.env.
    """
    sys.path.insert(0, os.path.join(REPO_DIR, 'tests', 'api'))
    from support import load_dump
    database = _local_db(_read_dev_env())
    counts = load_dump(database, os.path.join(DUMPS_DIR, dump),
                       replace=replace)
    for collection, count in counts.items():
        print(f'{collection:28s} {count:6d}')


@task(help={
    'dump': 'dump folder name in mongodb_collections_local (default 261001)',
    'assets': 'asset folder of the dump; step 6c then moves fixture files '
              'in a temporary copy',
    'mapping': 'also run step 11b with this untracked mapping file '
               '(e.g. .dev/reattribute_06.json)',
})
def rehearse(c, dump='261001', assets='', mapping=''):
    """
    Rehearse the 0.6 migration on a local dump in a throwaway mongod.
    """
    args = f' --assets "{assets}"' if assets else ''
    args += f' --mapping "{mapping}"' if mapping else ''
    with chdir(REPO_DIR):
        c.run(f'{sys.executable} scripts/db_maintenance/rehearse_06.py '
              f'--dump {dump}{args}', pty=False)


@task(help={
    'dump': 'dump folder name in mongodb_collections_local (default 261001)',
    'port': 'backend port (default 8000)',
    'mongo_port': 'throwaway mongod port (default 27018)',
    'derive': 'geometry-runner stages to run (default '
              'frame,shape_class,proxies,complexity); "none" skips them',
    'test_accounts': 'also create dev-contrib, dev-mod, dev-mod2, dev-rev '
                     'and dev-outsider (no role); passwords in '
                     '.dev/dev-test-accounts.json, not printed',
    'test_dataset': 'dataset of the test accounts (default dbu_zirkus)',
})
def dev_migrated(c, dump='261001', port=8000, mongo_port=27018,
                 derive='frame,shape_class,proxies,complexity',
                 test_accounts=False, test_dataset='dbu_zirkus'):
    """
    Serve a migrated copy of a dump (throwaway mongod) for frontend work.
    """
    flags = ' --no-derive' if derive == 'none' else f' --derive-stages {derive}'
    if test_accounts:
        flags += f' --test-accounts --test-dataset {test_dataset}'
    with chdir(REPO_DIR):
        c.run(f'{sys.executable} scripts/dev/serve_migrated.py --dump {dump} '
              f'--port {port} --mongo-port {mongo_port}{flags}', pty=False)


@task(help={
    'dry_run': 'report only, write nothing',
    'files': 'move fixture PLYs in the dev.env storage dirs (step 6c)',
})
def migrate_local(c, dry_run=False, files=False):
    """
    Run the 0.6 migration on the local database from dev.env.
    """
    env = _read_dev_env()
    _local_db(env)                       # refuses a non-local database
    flags = ' --dry-run' if dry_run else ''
    flags += '' if files else ' --no-files'
    with chdir(REPO_DIR):
        c.run(f'{sys.executable} scripts/db_maintenance/migrate_06.py --all '
              f'--uri "{env["MONGODB_URI"]}"{flags}', env=env, pty=False)


@task(help={
    'username': 'account name',
    'email': 'e-mail (any domain; the TU check applies to registration only)',
    'admin': 'give the account the global admin role',
})
def create_user(c, username, email, admin=False):
    """
    Create a verified account in the local database (password is prompted).
    """
    sys.path.insert(0, BACKEND_DIR)
    from apps.catalog.api.auth import get_password_hash
    database = _local_db(_read_dev_env())
    password = getpass.getpass(f'password for {username}: ')
    database['users'].insert_one({
        '_id': str(uuid.uuid4()),
        'username': username,
        'email': email.lower(),
        'full_name': username,
        'hashed_password': get_password_hash(password),
        'role': 'admin' if admin else 'user',
        'disabled': False,
        'email_verified': True,
    })
    print(f'created {"admin" if admin else "user"} {username}')


# RELEASES --------------------------------------------------------------------
# One product version for backend, web frontend and Grasshopper interface
# (VERSION file, tag v<version>). See README, "Releases and deployment".

def _rewrite(path, pattern, replacement, count=1):
    import re
    with open(path, encoding='utf-8', newline='') as handle:
        text = handle.read()
    new_text, n = re.subn(pattern, replacement, text, count=count,
                          flags=re.MULTILINE)
    if n == 0:
        sys.exit(f'bump-version: pattern not found in {path}: {pattern}')
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(new_text)


@task(help={
    'version': 'new version, e.g. 0.5.1.1 or 0.6.0.0-beta.1',
    'gh': 'the Grasshopper UserObjects changed too: move their client version',
})
def bump_version(c, version, gh=False):
    """
    Write a new CSC version everywhere it is recorded (then edit CHANGELOG).
    """
    import datetime
    import re
    if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?', version):
        sys.exit('version must look like 0.5.1.1 or 0.6.0.0-beta.1')
    v = r'\d+\.\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?'
    with open(os.path.join(REPO_DIR, 'VERSION'), 'w', encoding='utf-8',
              newline='\n') as fh:
        fh.write(version + '\n')
    _rewrite(os.path.join(BACKEND_DIR, 'csc_version.py'),
             rf"^CSC_VERSION = '{v}'", f"CSC_VERSION = '{version}'")
    frontend = os.path.join(REPO_DIR, 'src', 'frontend')
    _rewrite(os.path.join(frontend, 'package.json'),
             rf'^  "version": "{v}"', f'  "version": "{version}"')
    _rewrite(os.path.join(frontend, 'package-lock.json'),
             rf'^  "version": "{v}"', f'  "version": "{version}"')
    _rewrite(os.path.join(frontend, 'package-lock.json'),
             rf'^      "version": "{v}"', f'      "version": "{version}"')
    _rewrite(os.path.join(REPO_DIR, 'README.md'),
             rf'^- \*\*CSC\*\*: {v}([^`]*)tag `v{v}`',
             rf'- **CSC**: {version}\1tag `v{version}`')
    changelog = os.path.join(REPO_DIR, 'CHANGELOG.md')
    with open(changelog, encoding='utf-8') as fh:
        has_section = f'## [{version}]' in fh.read()
    if not has_section:
        _rewrite(changelog, r'^## \[', f'## [{version}] - unreleased\n\n## [')
    if gh:
        session = os.path.join(REPO_DIR, 'grasshopper_userobjects_src',
                               'DDU_CSC_Session.py')
        _rewrite(session, rf"^CSC_CLIENT = 'gh-userobjects/{v}'",
                 f"CSC_CLIENT = 'gh-userobjects/{version}'")
        _rewrite(session, r'^Version: \d+(\.\d+)?[a-z]?(?=\r?$)',
                 f"Version: {datetime.date.today():%y%m%d}")
        print('GH: CSC_Session changed -> re-export DDU_CSC_Session.ghuser '
              '(and its XML) in Rhino before releasing')
    print(f'VERSION -> {version}; now fill in the CHANGELOG section')
    with chdir(REPO_DIR):
        c.run(f'{sys.executable} scripts/ci/check_version.py', pty=False,
              warn=True)


@task(help={'check': 'only report, write nothing'})
def gh_headers(c, check=False):
    """
    Write the '# venv:' / '# r:' header of every Grasshopper component listed
    in grasshopper_lib/envs.json (the library itself is the package
    grasshopper_lib/csc_gh, decision 8.111; nothing is embedded).
    """
    sys.path.insert(0, os.path.join(REPO_DIR, 'grasshopper_lib'))
    import headers
    if check:
        problems = headers.check()
        print('\n'.join(problems) or 'headers are current')
        if problems:
            sys.exit(1)
        return
    changed = headers.sync()
    print('changed: ' + (', '.join(changed) or 'nothing'))


@task
def gh_frame_fixtures(c):
    """
    Let the server's compute_frame (apps/catalog/frame.py) rewrite the
    shared fixtures of the frame parity test (tests/fixtures/frame_parity).
    """
    with chdir(REPO_DIR):
        c.run(f'{sys.executable} tests/grasshopper/frame_cases.py --write',
              pty=False)


# CONTEXT ---------------------------------------------------------------------

@contextlib.contextmanager
def chdir(dirname=None):
    current_dir = os.getcwd()
    try:
        if dirname is not None:
            os.chdir(dirname)
        yield
    finally:
        os.chdir(current_dir)
