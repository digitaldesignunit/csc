"""
The one place in the backend that reads the environment (decision 8.156).

``Settings`` names every environment variable the backend and its cron entry
points read, with its type, its default and what it is for. ``get_settings()``
builds it once; a bad value stops the start with the name of the variable
(never its value: secrets are ``SecretStr``, and the error text carries no
input). Tests build their own ``Settings(...)`` or clear the cache with
``get_settings.cache_clear()`` instead of patching ``os.environ`` in code
that already ran.

The variables the API needs (``REQUIRED_FOR_API``) are checked by
``require_api()`` when the API starts; the cron entry points need less and
ask only for what they use (``Settings.require(...)``), so a cron job with a
partial environment still starts.

Stdlib and pydantic only: ``conf.py`` imports this module before the
application is loaded.
"""

from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from pydantic import (
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

MIN_JWT_SECRET_BYTES = 32
DEFAULT_WORKERS = 2
MAX_WORKERS = 8
LOG_LEVELS = ('debug', 'info', 'warning', 'error', 'critical')
DEFAULT_TRUSTED_PROXIES = '127.0.0.0/8,::1'
DEFAULT_MAX_DATASETS = 3
EVIDENCE_UPLOAD_MAX_MB = 25
LOCAL_HOSTS = ('localhost', '127.0.0.1', '::1')
RATE_LIMIT_SCHEMES = ('memory://', 'mongodb://', 'mongodb+srv://')

# what the API cannot start without (the list that main_fastapi.py carried)
REQUIRED_FOR_API = (
    'MONGODB_URI', 'JWT_SECRET', 'GITHUB_REPO_URL', 'SMTP_HOST', 'SMTP_USER',
    'SMTP_PASSWORD', 'SMTP_FROM_EMAIL', 'FRONTEND_URL',
    'SNAPSHOT_PREVIEW_DIR', 'SNAPSHOT_PHOTOS_DIR', 'SNAPSHOT_MESHES_DIR',
    'SNAPSHOT_POINT_CLOUDS_DIR', 'SNAPSHOT_PROXIES_DIR',
    'SNAPSHOT_CAPTURE_DIR', 'EVIDENCE_ATTACHMENTS_DIR', 'GH_XML_CACHE_DIR',
    'FASTAPI_CORS_ORIGINS',
)


class SettingsError(ValueError):
    """A setting is missing or wrong; the text names the variable, never its
    value."""


def jwt_secret_problem(secret: Optional[str]) -> Optional[str]:
    """Why ``secret`` cannot sign tokens, or None when it can (S10, 8.144):
    a short secret lets anyone who has seen one token try to forge others."""
    if len((secret or '').encode('utf-8')) < MIN_JWT_SECRET_BYTES:
        return (f'JWT_SECRET must be at least {MIN_JWT_SECRET_BYTES} bytes '
                f'(openssl rand -hex 32)')
    return None


def parse_trusted_proxies(text: str) -> Tuple[Any, ...]:
    """The networks of a ``CSC_TRUSTED_PROXIES`` list (comma separated
    addresses and networks); a bad entry stops the start with its name."""
    networks = []
    for item in (text or '').split(','):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError as exc:
            raise ValueError(
                f'CSC_TRUSTED_PROXIES: bad entry {item!r}') from exc
    return tuple(networks)


def _sanitize_path(path: str) -> str:
    return os.path.abspath(os.path.realpath(os.path.normpath(path)))


def _url(value: Optional[str], name: str) -> Optional[str]:
    if value is None:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError(f'{name} must be an http(s) URL')
    return value


class Settings(BaseSettings):
    """Every environment variable of the backend. The field ``x_y`` reads the
    variable ``X_Y``; an empty variable counts as not set."""

    model_config = SettingsConfigDict(
        extra='ignore', env_ignore_empty=True, case_sensitive=False,
        str_strip_whitespace=True)

    # DATABASE ---------------------------------------------------------------
    mongodb_uri: Optional[SecretStr] = Field(
        None, description='MongoDB connection string (holds credentials)')
    mongodb_db: str = Field('csc', description='MongoDB database name')

    # AUTHENTICATION ---------------------------------------------------------
    jwt_secret: Optional[SecretStr] = Field(
        None, description=f'key that signs the JWTs, at least '
                          f'{MIN_JWT_SECRET_BYTES} bytes')
    jwt_algorithm: str = Field(
        'HS256', description='JWT signing algorithm (only HS256 is accepted)')
    jwt_access_token_expire_minutes: int = Field(
        30, ge=1, description='lifetime of an access token in minutes')
    csc_open_registration_domains: str = Field(
        'tu-darmstadt.de', description='comma separated e-mail domains that '
                                       'may register without an invitation')
    csc_max_datasets_per_user: int = Field(
        DEFAULT_MAX_DATASETS, ge=0, description='datasets one account may '
        'create (admins: no limit); 3 when not a number')

    # E-MAIL -----------------------------------------------------------------
    smtp_host: Optional[str] = Field(None, description='SMTP server')
    smtp_port: int = Field(587, ge=1, le=65535, description='SMTP port')
    smtp_user: Optional[str] = Field(None, description='SMTP account')
    smtp_password: Optional[SecretStr] = Field(
        None, description='SMTP password')
    smtp_from_email: Optional[str] = Field(
        None, description='sender address of the mails')
    smtp_from_name: str = Field('Catalog of Second Chances',
                                description='sender name of the mails')
    smtp_reply_to: str = Field(
        '', description='support address where replies go; none when empty')
    smtp_dev_mode: bool = Field(
        False, description='write the mails to the log instead of sending '
        '(only the text "true" switches it on; refused unless FRONTEND_URL '
        'is localhost)')
    frontend_url: Optional[str] = Field(
        None, description='public address of the web app (links in mails, '
                          'JSON-LD context)')
    csc_public_api_url: str = Field(
        '', description='public address of the API for the links of exports '
                        '(optional)')

    # GITHUB / GRASSHOPPER UPDATE --------------------------------------------
    github_repo_url: Optional[str] = Field(
        None, description='GitHub repository that the CSC_Update serves')
    github_csc_gh_token: SecretStr = Field(
        SecretStr(''), description='optional GitHub token (rate limits)')
    gh_update_ref: str = Field(
        '', description='git ref CSC_Update reads instead of the release tag')
    gh_xml_cache_dir: Optional[str] = Field(
        None, description='cache folder of the UserObject XML')

    # CLIENTS ----------------------------------------------------------------
    csc_min_client_versions: str = Field(
        '', description='minimum client versions, "web=0.6.0.0,..."; empty: '
                        'log only')
    client_log_path: str = Field(
        os.path.join(BACKEND_DIR, 'logs', 'client_versions.log'),
        description='daily file of the X-CSC-Client log')
    fastapi_cors_origins: Optional[str] = Field(
        None, description='comma separated origins the browser may call from')
    csc_trusted_proxies: str = Field(
        DEFAULT_TRUSTED_PROXIES, description='peers whose X-Forwarded-For '
        'is believed (addresses and networks, comma separated)')
    csc_rate_limit_storage: Optional[SecretStr] = Field(
        None, description='where the rate limit counters live: memory:// or a '
        'MongoDB URI (holds credentials); the MongoDB URI of MONGODB_URI when '
        'not set (decision 8.152)')

    # FILES ------------------------------------------------------------------
    snapshot_preview_dir: Optional[str] = Field(
        None, description='rendered thumbnails')
    snapshot_photos_dir: Optional[str] = Field(
        None, description='uploaded photos')
    snapshot_meshes_dir: Optional[str] = Field(
        None, description='PLY mesh files')
    snapshot_point_clouds_dir: Optional[str] = Field(
        None, description='PLY point clouds')
    snapshot_proxies_dir: Optional[str] = Field(
        None, description='deviation maps')
    snapshot_capture_dir: Optional[str] = Field(
        None, description='capture fixtures')
    evidence_attachments_dir: Optional[str] = Field(
        None, description='evidence attachments')

    # LIMITS -----------------------------------------------------------------
    geometry_upload_limit_mb: int = Field(
        250, ge=1, description='largest geometry upload in MB')
    evidence_upload_limit_mb: int = Field(
        EVIDENCE_UPLOAD_MAX_MB, ge=1, le=EVIDENCE_UPLOAD_MAX_MB,
        description='largest evidence attachment in MB (may only lower 25)')
    snapshot_photo_upload_limit_mb: int = Field(
        10, ge=1, description='largest photo upload in MB')
    csc_json_body_limit_mb: int = Field(
        16, ge=1, description='largest request body of every route that takes '
        'no file, in MB (decision 8.163)')
    snapshot_photo_max_output_mb: int = Field(
        2, ge=1, description='largest stored photo in MB')
    snapshot_photo_max_long_edge_px: int = Field(
        4096, ge=1, description='longest edge of a stored photo in pixels')

    # SERVER AND RUNNER ------------------------------------------------------
    csc_workers: int = Field(
        DEFAULT_WORKERS, description='gunicorn workers, 1 to 8 (decision '
        '8.130); 2 when not a number')
    csc_log_level: str = Field(
        'info', description='log level: ' + ', '.join(LOG_LEVELS)
        + '; info when unknown')
    csc_geometry_heavy_stages: str = Field(
        'server', description='where the heavy geometry stages run: '
                              'server or remote (8.54)')
    csc_api_token: Optional[SecretStr] = Field(
        None, description='bearer token of the remote geometry runner')
    csc_api_password: Optional[SecretStr] = Field(
        None, description='password of the remote geometry runner')

    # VALIDATION -------------------------------------------------------------
    @field_validator('jwt_secret')
    @classmethod
    def _jwt_secret(cls, value: Optional[SecretStr]) -> Optional[SecretStr]:
        if value is not None:
            problem = jwt_secret_problem(value.get_secret_value())
            if problem:
                raise ValueError(problem)
        return value

    @field_validator('jwt_algorithm', mode='after')
    @classmethod
    def _jwt_algorithm(cls, value: str) -> str:
        if value != 'HS256':
            raise ValueError(
                f'JWT_ALGORITHM must be HS256, got {value!r}')
        return value

    @field_validator('csc_rate_limit_storage', mode='after')
    @classmethod
    def _rate_limit_storage(cls, value: Optional[SecretStr]
                            ) -> Optional[SecretStr]:
        if value is not None and not value.get_secret_value().startswith(
                RATE_LIMIT_SCHEMES):
            raise ValueError('CSC_RATE_LIMIT_STORAGE must be memory:// or a '
                             'mongodb:// URI')
        return value

    @field_validator('frontend_url', 'github_repo_url', mode='after')
    @classmethod
    def _required_url(cls, value: Optional[str], info) -> Optional[str]:
        return _url(value, info.field_name.upper())

    @field_validator('csc_public_api_url', mode='after')
    @classmethod
    def _optional_url(cls, value: str) -> str:
        return _url(value, 'CSC_PUBLIC_API_URL') if value else value

    @field_validator('snapshot_preview_dir', 'snapshot_photos_dir',
                     'snapshot_meshes_dir', 'snapshot_point_clouds_dir',
                     'snapshot_proxies_dir', 'snapshot_capture_dir',
                     'evidence_attachments_dir', 'gh_xml_cache_dir',
                     mode='after')
    @classmethod
    def _folder(cls, value: Optional[str]) -> Optional[str]:
        return _sanitize_path(value) if value else value

    @field_validator('smtp_dev_mode', mode='before')
    @classmethod
    def _dev_mode(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower() == 'true'
        return value

    @model_validator(mode='after')
    def _dev_mode_stays_local(self) -> 'Settings':
        # dev mode writes the mails, with their links, to the log: never on a
        # server whose web app has a public address
        if self.smtp_dev_mode and self.frontend_url is not None:
            host = urlsplit(self.frontend_url).hostname
            if host not in LOCAL_HOSTS:
                raise ValueError(
                    'SMTP_DEV_MODE is for local development only: FRONTEND_URL '
                    'must be localhost, 127.0.0.1 or ::1 while it is on')
        return self

    @field_validator('csc_max_datasets_per_user', mode='before')
    @classmethod
    def _max_datasets(cls, value: Any) -> Any:
        try:
            return max(0, int(str(value).strip()))
        except ValueError:
            return DEFAULT_MAX_DATASETS

    @field_validator('csc_workers', mode='before')
    @classmethod
    def _workers(cls, value: Any) -> Any:
        return worker_count(str(value))

    @field_validator('csc_log_level', mode='before')
    @classmethod
    def _level(cls, value: Any) -> Any:
        return log_level(str(value))

    @field_validator('csc_geometry_heavy_stages', mode='after')
    @classmethod
    def _heavy_stages(cls, value: str) -> str:
        value = value.lower()
        if value not in ('server', 'remote'):
            raise ValueError(
                f'CSC_GEOMETRY_HEAVY_STAGES must be server or remote, '
                f'got {value!r}')
        return value

    @field_validator('csc_trusted_proxies', mode='after')
    @classmethod
    def _proxies(cls, value: str) -> str:
        parse_trusted_proxies(value)
        return value

    # DERIVED VALUES AND CHECKS ----------------------------------------------
    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in (self.fastapi_cors_origins or '').split(',')
                if o.strip()]

    def require(self, *names: str) -> 'Settings':
        """Stop with the names of the given environment variables that are not
        set (each is checked as ``Settings.<name lower case>``)."""
        missing = [n for n in names if not getattr(self, n.lower())
                   or (isinstance(getattr(self, n.lower()), SecretStr)
                       and not getattr(self, n.lower()).get_secret_value())]
        if missing:
            raise SettingsError(
                f'Missing required environment variables: {missing}')
        return self

    def require_api(self) -> 'Settings':
        return self.require(*REQUIRED_FOR_API)

    def need(self, name: str) -> str:
        """The value of one required variable as text (a secret unwrapped)."""
        self.require(name)
        value = getattr(self, name.lower())
        return value.get_secret_value() if isinstance(value, SecretStr) \
            else value

    @property
    def rate_limit_uri(self) -> str:
        """The store of the rate limit counters (decision 8.152): the
        variable, else the database of the API."""
        if self.csc_rate_limit_storage is not None:
            return self.csc_rate_limit_storage.get_secret_value()
        return self.need('MONGODB_URI')

    def trusted_networks(self) -> Tuple[Any, ...]:
        return parse_trusted_proxies(self.csc_trusted_proxies)


def worker_count(raw: str) -> int:
    """``CSC_WORKERS`` (decision 8.130): a whole number from 1 to 8; two when
    it is empty or not a number. Every worker loads the geometry libraries, so
    the number follows the memory of the account, not the number of cores."""
    try:
        value = int((raw or '').strip())
    except ValueError:
        return DEFAULT_WORKERS
    return min(max(value, 1), MAX_WORKERS)


def log_level(raw: str) -> str:
    """``CSC_LOG_LEVEL`` (decision 8.130): one of gunicorn's levels, ``info``
    when it is empty or unknown."""
    text = (raw or '').strip().lower()
    return text if text in LOG_LEVELS else 'info'


def _message(errors: List[Dict[str, Any]]) -> str:
    lines = []
    for error in errors:
        name = str(error['loc'][0]).upper() if error['loc'] else ''
        text = str(error['msg'])
        if text.startswith('Value error, '):
            text = text[len('Value error, '):]
        lines.append(text if not name or text.startswith(name)
                     else f'{name}: {text}')
    return '; '.join(lines)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The settings of this process, read from the environment once."""
    try:
        return Settings()
    except ValidationError as exc:
        # no input in the text: a secret must not reach a log or a terminal
        raise SettingsError(_message(
            exc.errors(include_input=False, include_url=False,
                       include_context=False))) from None
