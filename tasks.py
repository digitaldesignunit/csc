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


@task(help={
    'k': 'only run tests matching this expression (pytest -k)',
    'dump': 'also run the dump smoke test against mongodb_collections_local/<dump>',
})
def test(c, k='', dump=''):
    """
    Run the test suite (unit tests + route tests on a throwaway mongod).
    """
    env = {}
    if dump:
        env['CSC_DUMP_DIR'] = os.path.join(DUMPS_DIR, dump)
    selection = f' -k "{k}"' if k else ''
    with chdir(REPO_DIR):
        c.run(f'{sys.executable} -m pytest tests{selection}', env=env,
              pty=False)


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
