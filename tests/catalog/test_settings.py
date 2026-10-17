"""The settings object (decision 8.156): every variable named once, typed,
defaulted and checked at the start; no secret in a message."""

from __future__ import annotations

import os

import pytest
from pydantic import SecretStr

import settings as st
from settings import Settings, SettingsError, get_settings

FOLDERS = ('SNAPSHOT_PREVIEW_DIR', 'SNAPSHOT_PHOTOS_DIR', 'SNAPSHOT_MESHES_DIR',
           'SNAPSHOT_POINT_CLOUDS_DIR', 'SNAPSHOT_PROXIES_DIR',
           'SNAPSHOT_CAPTURE_DIR', 'EVIDENCE_ATTACHMENTS_DIR', 'GH_XML_CACHE_DIR')
SECRET = 'a-secret-of-at-least-thirty-two-bytes!'


@pytest.fixture
def clean(env):
    """No variable of the backend in the environment."""
    env(**{name.upper(): None for name in Settings.model_fields})


@pytest.fixture
def full(clean, env, tmp_path):
    """A complete API environment."""
    values = {
        'MONGODB_URI': 'mongodb://user:db-password@127.0.0.1:27017/csc',
        'JWT_SECRET': SECRET, 'GITHUB_REPO_URL': 'https://github.com/o/r',
        'SMTP_HOST': 'smtp.example.org', 'SMTP_USER': 'mailer',
        'SMTP_PASSWORD': 'smtp-password', 'SMTP_FROM_EMAIL': 'n@example.org',
        'FRONTEND_URL': 'https://csc.example.org',
        'FASTAPI_CORS_ORIGINS': 'https://a.example.org, http://localhost:3000',
        **{name: str(tmp_path / name.lower()) for name in FOLDERS}}
    env(**values)
    return values


def test_every_variable_has_a_one_line_description():
    for name, field in Settings.model_fields.items():
        assert field.description, name
        assert '\n' not in field.description, name


def test_the_defaults_are_the_ones_the_backend_always_had(clean):
    s = get_settings()
    assert (s.mongodb_db, s.jwt_algorithm, s.jwt_access_token_expire_minutes) == ('csc', 'HS256', 30)
    assert (s.smtp_port, s.smtp_from_name, s.smtp_reply_to, s.smtp_dev_mode) == (
        587, 'Catalog of Second Chances', '', False)
    assert (s.csc_workers, s.csc_log_level, s.csc_max_datasets_per_user) == (2, 'info', 3)
    assert s.csc_open_registration_domains == 'tu-darmstadt.de'
    assert s.csc_trusted_proxies == '127.0.0.0/8,::1'
    assert s.csc_geometry_heavy_stages == 'server'
    assert (s.geometry_upload_limit_mb, s.evidence_upload_limit_mb) == (250, 25)
    assert (s.snapshot_photo_upload_limit_mb, s.snapshot_photo_max_output_mb,
            s.snapshot_photo_max_long_edge_px) == (10, 2, 4096)
    assert s.csc_json_body_limit_mb == 16
    assert s.csc_rate_limit_storage is None
    assert s.csc_min_client_versions == '' and s.csc_public_api_url == ''
    assert s.client_log_path.endswith('client_versions.log')
    assert s.github_csc_gh_token.get_secret_value() == ''


def test_the_api_needs_its_seventeen_variables_and_names_the_missing_ones(clean):
    assert len(st.REQUIRED_FOR_API) == 17
    with pytest.raises(SettingsError) as stop:
        get_settings().require_api()
    for name in st.REQUIRED_FOR_API:
        assert name in str(stop.value)


def test_a_complete_environment_passes_and_empty_counts_as_unset(full, env):
    s = get_settings().require_api()
    assert s.cors_origins == ['https://a.example.org', 'http://localhost:3000']
    env(SMTP_HOST='')
    with pytest.raises(SettingsError, match='SMTP_HOST'):
        get_settings().require_api()


def test_a_cron_job_asks_only_for_what_it_uses(clean, env):
    env(MONGODB_URI='mongodb://127.0.0.1/x')
    assert get_settings().need('MONGODB_URI') == 'mongodb://127.0.0.1/x'
    with pytest.raises(SettingsError, match='SNAPSHOT_MESHES_DIR'):
        get_settings().need('SNAPSHOT_MESHES_DIR')


def test_folders_become_absolute_paths(full, tmp_path):
    for name in FOLDERS:
        assert get_settings().need(name) == str(tmp_path / name.lower())
    relative = Settings(snapshot_meshes_dir='relative/meshes').snapshot_meshes_dir
    assert os.path.isabs(relative) and relative.endswith('meshes')


def test_secrets_never_show_in_a_printed_settings_object(full):
    s = get_settings()
    shown = repr(s) + str(s) + str(s.model_dump())
    for secret in (SECRET, 'db-password', 'smtp-password'):
        assert secret not in shown
    assert s.need('JWT_SECRET') == SECRET and s.jwt_secret.get_secret_value() == SECRET
    assert isinstance(s.smtp_password, SecretStr)


@pytest.mark.parametrize('secret, bad', [('x' * 31, True), ('x' * 32, False), ('\u00e4' * 15, True)])
def test_the_jwt_secret_needs_thirty_two_bytes(clean, env, secret, bad):
    env(JWT_SECRET=secret)
    if bad:
        with pytest.raises(SettingsError, match='JWT_SECRET must be at least 32 bytes') as stop:
            get_settings()
        assert secret not in str(stop.value)                      # the value is never in the text
    else:
        assert get_settings().jwt_secret is not None


@pytest.mark.parametrize('name, value', [
    ('FRONTEND_URL', 'not a url'), ('FRONTEND_URL', 'ftp://example.org'),
    ('GITHUB_REPO_URL', 'github.com/o/r'), ('CSC_PUBLIC_API_URL', 'api.example.org'),
])
def test_a_bad_url_stops_the_start_with_its_name(clean, env, name, value):
    env(**{name: value})
    with pytest.raises(SettingsError, match=name):
        get_settings()


@pytest.mark.parametrize('name, value', [
    ('GEOMETRY_UPLOAD_LIMIT_MB', '0'), ('GEOMETRY_UPLOAD_LIMIT_MB', '-5'),
    ('EVIDENCE_UPLOAD_LIMIT_MB', '0'), ('EVIDENCE_UPLOAD_LIMIT_MB', '26'),
    ('SNAPSHOT_PHOTO_UPLOAD_LIMIT_MB', '0'), ('SNAPSHOT_PHOTO_MAX_OUTPUT_MB', '0'),
    ('SNAPSHOT_PHOTO_MAX_LONG_EDGE_PX', '0'), ('SNAPSHOT_PHOTO_MAX_LONG_EDGE_PX', 'wide'),
    ('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '0'), ('SMTP_PORT', '70000'),
    ('CSC_JSON_BODY_LIMIT_MB', '0'), ('CSC_JSON_BODY_LIMIT_MB', 'big'),
])
def test_a_limit_must_be_a_positive_number(clean, env, name, value):
    env(**{name: value})
    with pytest.raises(SettingsError, match=name):
        get_settings()


def test_the_evidence_limit_may_only_lower_the_maximum(clean, env):
    env(EVIDENCE_UPLOAD_LIMIT_MB='25')
    assert get_settings().evidence_upload_limit_mb == 25
    env(EVIDENCE_UPLOAD_LIMIT_MB='5')
    assert get_settings().evidence_upload_limit_mb == 5


@pytest.mark.parametrize('raw, workers', [('3', 3), (' 4 ', 4), ('0', 1), ('64', 8), ('two', 2), ('', 2)])
def test_the_worker_count_keeps_its_limits(clean, env, raw, workers):
    env(CSC_WORKERS=raw)
    assert get_settings().csc_workers == workers


@pytest.mark.parametrize('raw, level', [('WARNING', 'warning'), (' debug ', 'debug'),
                                        ('verbose', 'info'), ('', 'info')])
def test_the_log_level_is_one_of_gunicorns_or_info(clean, env, raw, level):
    env(CSC_LOG_LEVEL=raw)
    assert get_settings().csc_log_level == level


@pytest.mark.parametrize('raw, expected', [('true', True), ('TRUE', True), (' True ', True),
                                           ('false', False), ('1', False), ('yes', False)])
def test_only_the_text_true_switches_dev_mode_on(clean, env, raw, expected):
    env(SMTP_DEV_MODE=raw)
    assert get_settings().smtp_dev_mode is expected


@pytest.mark.parametrize('raw, expected', [('2', 2), ('0', 0), ('-1', 0), ('many', 3), ('2.5', 3)])
def test_the_dataset_limit_falls_back_to_three(clean, env, raw, expected):
    env(CSC_MAX_DATASETS_PER_USER=raw)
    assert get_settings().csc_max_datasets_per_user == expected


def test_the_heavy_stage_setting_is_server_or_remote(clean, env):
    env(CSC_GEOMETRY_HEAVY_STAGES=' Remote ')
    assert get_settings().csc_geometry_heavy_stages == 'remote'
    env(CSC_GEOMETRY_HEAVY_STAGES='cloud')
    with pytest.raises(SettingsError, match='CSC_GEOMETRY_HEAVY_STAGES must be server or remote'):
        get_settings()


def test_the_rate_limit_store_defaults_to_the_database_of_the_api(full, env):
    s = get_settings()
    assert s.rate_limit_uri == s.need('MONGODB_URI')
    env(CSC_RATE_LIMIT_STORAGE='memory://')
    assert get_settings().rate_limit_uri == 'memory://'
    env(CSC_RATE_LIMIT_STORAGE='mongodb://other.example.org:27017/counters')
    assert get_settings().rate_limit_uri == 'mongodb://other.example.org:27017/counters'


def test_a_rate_limit_store_with_credentials_does_not_reach_a_message(clean, env):
    env(CSC_RATE_LIMIT_STORAGE='redis://user:store-password@host')
    with pytest.raises(SettingsError) as stop:
        get_settings()
    assert 'CSC_RATE_LIMIT_STORAGE' in str(stop.value)
    assert 'store-password' not in str(stop.value)


def test_only_hs256_is_a_signing_algorithm(clean, env):
    env(JWT_ALGORITHM='HS512')
    with pytest.raises(SettingsError, match='JWT_ALGORITHM must be HS256'):
        get_settings()
    env(JWT_ALGORITHM='HS256')
    assert get_settings().jwt_algorithm == 'HS256'


def test_a_bad_trusted_proxy_entry_names_the_variable(clean, env):
    env(CSC_TRUSTED_PROXIES='127.0.0.1, *')
    with pytest.raises(SettingsError, match="CSC_TRUSTED_PROXIES: bad entry '[*]'"):
        get_settings()


def test_the_settings_are_read_once_and_a_test_builds_its_own(clean, env):
    env(MONGODB_DB='first')
    first = get_settings()
    os.environ['MONGODB_DB'] = 'second'
    assert get_settings() is first and first.mongodb_db == 'first'          # cached
    assert Settings(mongodb_db='mine').mongodb_db == 'mine'                 # built directly
    get_settings.cache_clear()
    assert get_settings().mongodb_db == 'second'


@pytest.mark.parametrize('url, ok', [
    ('http://localhost:3000', True), ('http://127.0.0.1:3000', True), ('http://[::1]:3000', True),
    ('https://2ndchances.build', False), ('http://localhost.example.org', False)])
def test_dev_mode_is_refused_unless_the_web_app_is_local(clean, env, url, ok):
    env(SMTP_DEV_MODE='true', FRONTEND_URL=url)
    if ok:
        assert get_settings().smtp_dev_mode is True
    else:
        with pytest.raises(SettingsError, match='SMTP_DEV_MODE is for local development only'):
            get_settings()


def test_dev_mode_off_or_no_address_needs_nothing(clean, env):
    env(SMTP_DEV_MODE='true')
    assert get_settings().smtp_dev_mode is True               # no FRONTEND_URL: the API start asks for it
    env(SMTP_DEV_MODE='false', FRONTEND_URL='https://2ndchances.build')
    assert get_settings().smtp_dev_mode is False
