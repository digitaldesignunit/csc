#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import time
import json
import base64
import os
import hashlib
from threading import RLock
import uuid
from datetime import datetime, timedelta

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'SignIn'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'SignIn'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '1 User'  # type: ignore[reportUnedfinedVariable] # NOQA

"""
Author: Max Benjamin Eschenbach
License: MIT License
Version: 250904
"""


# ComponentCache - Embedded ---------------------------------------------------

class _ComponentCache(object):
    """
    Component cache manager for efficient local storage and retrieval.

    Author: Max Benjamin Eschenbach
    License: MIT License
    """

    def __init__(self, cache_dir=None, ttl_hours=24):
        self.ttl_hours = ttl_hours
        self.cache_dir = cache_dir or self._get_default_cache_dir()
        self.components_dir = os.path.join(self.cache_dir, 'components')
        self.metadata_dir = os.path.join(self.cache_dir, 'metadata')
        self._lock = RLock()

        # Ensure cache directories exist
        self._ensure_cache_dirs()

    def _get_default_cache_dir(self):
        """Get platform-specific cache directory."""
        if os.name == 'nt':  # Windows
            appdata = os.environ.get('APPDATA', '')
            return os.path.join(appdata, 'DDU_CSC', 'cache')
        else:  # macOS/Linux
            home = os.path.expanduser('~')
            return os.path.join(home, 'Library', 'Application Support',
                                'DDU_CSC', 'cache')

    def _ensure_cache_dirs(self):
        """Create cache directories if they don't exist."""
        dirs = [self.cache_dir, self.components_dir, self.metadata_dir]
        for directory in dirs:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

    def _get_cache_key_hash(self, cache_key):
        """Generate a safe filename from cache key."""
        return hashlib.md5(cache_key.encode('utf-8')).hexdigest()

    def _is_expired(self, timestamp_str):
        """Check if cache entry is expired based on TTL."""
        try:
            timestamp = datetime.fromisoformat(
                timestamp_str.replace('Z', '+00:00'))
            expiry = timestamp + timedelta(hours=self.ttl_hours)
            return datetime.now(timestamp.tzinfo) > expiry
        except (ValueError, TypeError):
            return True  # If we can't parse timestamp, consider expired

    def get(self, cache_key, filters=None):
        """
        Get cached data for a cache key.

        Args:
            cache_key: Cache key (e.g., 'all_components', 'component:uuid')
            filters: Optional filter parameters for metadata cache

        Returns:
            Tuple of (data, etag, is_from_cache) or
            (None, None, False) if not found
        """
        with self._lock:
            try:
                # Check metadata cache first
                metadata_file = os.path.join(
                    self.metadata_dir,
                    f"{self._get_cache_key_hash(cache_key)}.json"
                )

                if not os.path.exists(metadata_file):
                    return None, None, False

                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                # Check if expired
                if self._is_expired(metadata.get('cached_at', '')):
                    return None, None, False

                # Handle different cache key types
                if cache_key.startswith('component:'):
                    # Individual component
                    component_id = cache_key.split(':', 1)[1]
                    component_file = os.path.join(
                        self.components_dir, f"{component_id}.json"
                    )

                    if os.path.exists(component_file):
                        with open(component_file, 'r', encoding='utf-8') as f:
                            component_data = json.load(f)
                        return component_data, metadata.get('etag'), True

                elif (cache_key == 'all_components' or
                        cache_key.startswith('filtered:')):
                    # Collection of components
                    components = []
                    for comp_ref in metadata.get('components', []):
                        comp_id = comp_ref.get('id')
                        if comp_id:
                            comp_file = os.path.join(
                                self.components_dir, f"{comp_id}.json"
                            )
                            if os.path.exists(comp_file):
                                with open(
                                    comp_file, 'r',
                                    encoding='utf-8'
                                ) as f:
                                    components.append(json.load(f))

                    return components, metadata.get('etag'), True

                elif cache_key == 'schema:component':
                    # Schema data is stored directly in metadata
                    return metadata.get('data'), metadata.get('etag'), True

                return None, None, False

            except (IOError, json.JSONDecodeError, KeyError):
                return None, None, False

    def set(self, cache_key, data, etag=None, filters=None):
        """
        Store data in cache.

        Args:
            cache_key: Cache key
            data: Data to cache
            etag: ETag for the data
            filters: Optional filter parameters
        """
        with self._lock:
            try:
                current_time = datetime.now().isoformat()

                if cache_key.startswith('component:'):
                    # Individual component
                    component_id = cache_key.split(':', 1)[1]
                    component_file = os.path.join(
                        self.components_dir, f"{component_id}.json"
                    )

                    # Store component data
                    with open(component_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                    # Store metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'component'
                    }

                elif (cache_key == 'all_components' or
                        cache_key.startswith('filtered:')):
                    # Collection of components
                    components = []
                    for component in data:
                        comp_id = component.get('_id') or component.get('id')
                        if comp_id:
                            # Store individual component
                            comp_file = os.path.join(
                                self.components_dir, f"{comp_id}.json"
                            )
                            with open(comp_file, 'w', encoding='utf-8') as f:
                                json.dump(
                                    component,
                                    f,
                                    indent=2,
                                    ensure_ascii=False
                                )

                            # Add reference to metadata
                            components.append({
                                'id': comp_id,
                                'etag': component.get('etag'),
                                'lastmodified': component.get('lastmodified')
                            })

                    # Store metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'collection',
                        'components': components,
                        'filters': filters
                    }

                elif cache_key == 'schema:component':
                    # Schema data - store directly in metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'schema',
                        'data': data
                    }

                # Write metadata file
                metadata_file = os.path.join(
                    self.metadata_dir,
                    f"{self._get_cache_key_hash(cache_key)}.json"
                )
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

            except (IOError, KeyError):
                # Silently fail cache writes to not break main functionality
                pass

    def invalidate(self, pattern=None):
        """
        Invalidate cache entries.

        Args:
            pattern: Optional pattern to match cache keys (None = clear all)
        """
        with self._lock:
            try:
                if pattern is None:
                    # Clear all cache
                    for directory in [self.components_dir, self.metadata_dir]:
                        for filename in os.listdir(directory):
                            file_path = os.path.join(directory, filename)
                            if os.path.isfile(file_path):
                                os.remove(file_path)
                else:
                    # Clear specific pattern
                    pattern_hash = self._get_cache_key_hash(pattern)
                    metadata_file = os.path.join(
                        self.metadata_dir, f"{pattern_hash}.json"
                    )
                    if os.path.exists(metadata_file):
                        os.remove(metadata_file)

            except (IOError, OSError):
                pass

    def get_cache_stats(self):
        """Get cache statistics."""
        with self._lock:
            try:
                component_count = len(
                    [f for f in os.listdir(self.components_dir)
                     if f.endswith('.json')]
                )
                metadata_count = len(
                    [f for f in os.listdir(self.metadata_dir)
                     if f.endswith('.json')]
                )

                # Calculate total cache size
                total_size = 0
                for directory in [self.components_dir, self.metadata_dir]:
                    for filename in os.listdir(directory):
                        file_path = os.path.join(directory, filename)
                        if os.path.isfile(file_path):
                            total_size += os.path.getsize(file_path)

                return {
                    'component_count': component_count,
                    'metadata_count': metadata_count,
                    'total_size_bytes': total_size,
                    'cache_dir': self.cache_dir
                }
            except (IOError, OSError):
                return {
                    'component_count': 0,
                    'metadata_count': 0,
                    'total_size_bytes': 0,
                    'cache_dir': self.cache_dir
                }


# AuthCore - Embedded ---------------------------------------------------------

class _AuthCore(object):
    """
    Authorization and cache management tool that gets stored in sticky to be
    used by other CSC Grasshopper Components.

    Author: Max Benjamin Eschenbach
    License: MIT License
    """

    def __init__(self, base_url, leeway=30, disable_cache=False):
        self.base_url = (base_url or 'https://api.ddu.uber.space').rstrip('/')
        self.leeway = int(leeway) if leeway is not None else 30
        self.disable_cache = disable_cache
        self._lock = RLock()
        self._token = None
        self._exp = 0
        self._username = None
        self._cache = None if disable_cache else _ComponentCache()

    @staticmethod
    def _now():
        return int(time.time())

    @staticmethod
    def _b64url_decode(seg):
        rem = len(seg) % 4
        if rem:
            seg += '=' * (4 - rem)
        return base64.urlsafe_b64decode(seg.encode('utf-8'))

    @classmethod
    def _jwt_payload(cls, token):
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return {}
            return json.loads(cls._b64url_decode(parts[1]).decode('utf-8'))
        except Exception:
            return {}

    def set_access_token(self, token, username=None):
        payload = self._jwt_payload(token)
        exp = int(payload.get('exp', 0))
        if exp <= 0:
            exp = self._now() + 3600  # 1h fallback if no exp claim
        with self._lock:
            self._token = token
            self._exp = exp
            if username:
                self._username = username

    def clear(self):
        with self._lock:
            self._token = None
            self._exp = 0
            self._username = None

    def is_valid(self):
        with self._lock:
            if not self._token or self._exp <= 0:
                return False
            return (self._now() + self.leeway) < self._exp

    def get_username(self):
        with self._lock:
            return self._username

    def auth_header(self):
        with self._lock:
            return ({'Authorization': 'Bearer ' + self._token}
                    if self._token else {})

    def authorized_get(
            self,
            path,
            params=None,
            extra_headers=None,
            timeout=20):
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )
        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)
        return requests.get(
            self.base_url + path,
            params=params,
            headers=headers,
            timeout=timeout
        )

    def authorized_post(
            self,
            path,
            json_body=None,
            files=None,
            extra_headers=None,
            timeout=60):
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )
        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)
        # Handle file uploads vs JSON requests
        if files is not None:
            # For file uploads, don't set Content-Type header
            # (let requests handle it)
            # and use data instead of json
            return requests.post(
                self.base_url + path,
                files=files,
                headers=headers,
                timeout=timeout
            )
        else:
            # For JSON requests, use json parameter
            return requests.post(
                self.base_url + path,
                json=json_body,
                headers=headers,
                timeout=timeout
            )

    def validate_uuid(self, uuid_to_test: str, version: int = 4):
        """
        Check if uuid_to_test is a valid UUID.
        Returns True if uuid_to_test is a valid UUID, otherwise False.
        """
        try:
            uuid_obj = uuid.UUID(uuid_to_test, version=version)
        except ValueError:
            return False
        return str(uuid_obj) == uuid_to_test

    # Cache Management Methods ------------------------------------------------

    def get_cache(self):
        """Get the cache instance."""
        return self._cache

    def set_cache_enabled(self, enabled):
        """Enable or disable caching."""
        with self._lock:
            self.disable_cache = not enabled
            if enabled and self._cache is None:
                self._cache = _ComponentCache()
            elif not enabled:
                self._cache = None

    def is_cache_enabled(self):
        """Check if caching is enabled."""
        return self._cache is not None

    def sync_cache(self):
        """Force cache synchronization (clear cache)."""
        if self._cache:
            self._cache.invalidate()

    def get_cache_stats(self):
        """Get cache statistics."""
        if self._cache:
            return self._cache.get_cache_stats()
        return {
            'component_count': 0,
            'metadata_count': 0,
            'total_size_bytes': 0,
            'cache_dir': 'Cache disabled'
        }

    def cached_get(
            self,
            path,
            cache_key,
            params=None,
            extra_headers=None,
            timeout=20):
        """
        Make a cached GET request with ETag support.

        Args:
            path: API path
            cache_key: Cache key for this request
            params: Query parameters
            extra_headers: Additional headers
            timeout: Request timeout

        Returns:
            Response object
        """
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )

        # If cache is disabled, make regular request
        if not self._cache:
            return self.authorized_get(path, params, extra_headers, timeout)

        # Check cache first
        cached_data, cached_etag, is_from_cache = self._cache.get(cache_key)

        # Prepare headers
        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)

        # Add conditional request header if we have cached data
        if is_from_cache and cached_etag:
            headers['If-None-Match'] = cached_etag

        # Make request
        response = requests.get(
            self.base_url + path,
            params=params,
            headers=headers,
            timeout=timeout
        )

        # Handle response
        if response.status_code == 304 and is_from_cache:
            # Not modified - return cached data
            # Create a mock response with cached data
            class MockResponse:
                def __init__(self, data, etag):
                    self.status_code = 200
                    self._data = data
                    self._etag = etag

                def json(self):
                    return self._data

                @property
                def headers(self):
                    return {'ETag': self._etag} if self._etag else {}

            return MockResponse(cached_data, cached_etag)

        elif response.status_code == 200:
            # Data changed or first request - cache the response
            try:
                data = response.json()
                etag = response.headers.get('ETag')
                self._cache.set(cache_key, data, etag, params)
            except (ValueError, KeyError):
                # If we can't parse JSON or cache, just return response
                pass

        return response

    def get_component_schema(self, force_refresh=False):
        """
        Get component schema with caching support.

        Args:
            force_refresh: Force refresh of schema even if cached

        Returns:
            Component schema dictionary or None if failed
        """
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )

        # If cache is disabled, make regular request
        # (schema endpoint is unprotected)
        if not self._cache:
            try:
                response = requests.get(f'{self.base_url}/schema/component')
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception:
                return None

        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_schema, cached_etag, is_from_cache = self._cache.get(
                'schema:component')
            if is_from_cache:
                return cached_schema

        # Make request to get schema (unprotected endpoint)
        try:
            # Prepare headers for conditional request
            headers = {}
            if not force_refresh:
                cached_schema, cached_etag, is_from_cache = self._cache.get(
                    'schema:component')
                if is_from_cache and cached_etag:
                    headers['If-None-Match'] = cached_etag

            response = requests.get(f'{self.base_url}/schema/component',
                                    headers=headers)

            if response.status_code == 304 and not force_refresh:
                # Not modified - return cached data
                cached_schema, _, is_from_cache = self._cache.get(
                    'schema:component')
                if is_from_cache:
                    return cached_schema

            elif response.status_code == 200:
                # Data changed or first request - cache the response
                try:
                    data = response.json()
                    etag = response.headers.get('ETag')
                    self._cache.set('schema:component', data, etag)
                    return data
                except (ValueError, KeyError):
                    return None

            return None
        except Exception:
            # If request fails and we have cached schema, return cached version
            if not force_refresh:
                cached_schema, _, is_from_cache = self._cache.get(
                    'schema:component')
                if is_from_cache:
                    return cached_schema
            return None


# SignIn Grasshopper Component ------------------------------------------------

class CSC_SignIn(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    """

    # Development setting - do not change!
    __HARD_RESET = False

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

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage or create new one."""
        if not self.__HARD_RESET:
            auth_core = sc.sticky.get('CSC_AuthCore')
        else:
            auth_core = None
        if auth_core is None:
            # Create new AuthCore instance with default settings
            auth_core = _AuthCore(base_url='https://api.ddu.uber.space')
            sc.sticky['CSC_AuthCore'] = auth_core
        return auth_core

    def RunScript(self,
            Username: str,
            Password: str,
            Refresh: bool,
            DisableCache,
            ClearCache):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = 'Your Username or E-Mail'
        self.InputParams[1].Description = 'Your password'
        self.InputParams[2].Description = (
            'Refresh toggle, press when your token expired'
        )
        self.InputParams[3].Description = (
            'Disable caching (default: False - caching enabled)'
        )
        self.InputParams[4].Description = (
            'Clear cache (default: False)'
        )

        # Initialize status messages list
        status_messages = []

        # Sanitize input parameters (defaults don't work in function signature)
        if DisableCache is None:
            DisableCache = False
        if ClearCache is None:
            ClearCache = False

        # Get or create AuthCore instance
        auth_core = self.get_auth_core_from_sticky()

        # Handle cache management
        if ClearCache:
            auth_core.sync_cache()
            status_messages.append('Cache cleared')
            self.Component.Message = 'Cache cleared'
            # Return status messages
            Status = status_messages
            return (Status,)

        # Set cache enabled/disabled
        auth_core.set_cache_enabled(not DisableCache)

        # Input validation
        if not Username or not Username.strip():
            status_messages.append('Please provide username/email')
            self.Component.Message = 'Please provide username/email'
            Status = status_messages
            return (Status,)

        if not Password or not Password.strip():
            status_messages.append('Please provide password')
            self.Component.Message = 'Please provide password'
            Status = status_messages
            return (Status,)

        username = Username.strip()
        password = Password.strip()

        try:
            if Refresh:
                # Refresh authentication - clear existing token and re-auth
                auth_core.clear()
                self.Component.Message = 'Refreshing authentication...'
            else:
                # Check if we already have a valid token
                if auth_core.is_valid():
                    current_user = auth_core.get_username()
                    self.Component.Message = (
                        f'Already signed in as: {current_user}'
                    )

                    # Fetch and cache component schema
                    try:
                        schema = auth_core.get_component_schema()
                        if schema:
                            status_messages.append(
                                'Schema cached successfully')
                            self._addRemark('Schema cached successfully')
                        else:
                            status_messages.append('Failed to cache schema')
                            self._addWarning('Failed to cache schema')
                    except Exception as e:
                        status_messages.append(
                            f'Schema caching failed: {str(e)}')
                        self._addWarning(f'Schema cache failed: {str(e)}')

                    # Get cache status for output
                    cache_stats = auth_core.get_cache_stats()
                    cache_enabled = auth_core.is_cache_enabled()
                    comp_count = cache_stats["component_count"]
                    size_kb = cache_stats["total_size_bytes"] // 1024

                    # Add cache status to messages
                    cache_status = (
                        f'Cache: {"Enabled" if cache_enabled else "Disabled"}'
                        f' | Components: {comp_count} | Size: {size_kb}KB')
                    status_messages.append(cache_status)
                    Status = status_messages
                    return (Status,)

                self.Component.Message = 'Signing in...'

            # Prepare login data
            login_data = {
                'username': username,
                'password': password
            }

            # Make login request
            response = requests.post(
                f'{auth_core.base_url}/auth/token',
                data=login_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                timeout=20
            )

            if response.status_code == 200:
                # Login successful
                token_data = response.json()
                access_token = token_data.get('access_token')

                if access_token:
                    # Store token in AuthCore
                    auth_core.set_access_token(access_token, username)

                    # Update sticky storage
                    sc.sticky['CSC_AuthCore'] = auth_core

                    # Fetch and cache component schema
                    try:
                        schema = auth_core.get_component_schema()
                        if schema:
                            status_messages.append(
                                'Schema cached successfully')
                            self._addRemark('Schema cached successfully')
                        else:
                            status_messages.append('Failed to cache schema')
                            self._addWarning('Failed to cache schema')
                    except Exception as e:
                        status_messages.append(
                            f'Schema caching failed: {str(e)}')
                        self._addWarning(f'Schema cache failed: {str(e)}')

                    # Get cache status for output
                    cache_stats = auth_core.get_cache_stats()
                    cache_enabled = auth_core.is_cache_enabled()
                    comp_count = cache_stats["component_count"]
                    size_kb = cache_stats["total_size_bytes"] // 1024

                    # Add cache status to messages
                    cache_status = (
                        f'Cache: {"Enabled" if cache_enabled else "Disabled"}'
                        f' | Components: {comp_count} | Size: {size_kb}KB')
                    status_messages.append(cache_status)

                    self.Component.Message = f'Signed in as: {username}'

                    # Return status messages
                    Status = status_messages
                    return (Status,)

                else:
                    msg = 'Login failed: No token received'
                    status_messages.append(msg)
                    self._addWarning(msg)
                    self.Component.Message = msg
                    Status = status_messages
                    return (Status,)

            elif response.status_code == 401:
                msg = 'Invalid username or password'
                status_messages.append(msg)
                self._addError(msg)
                self.Component.Message = msg
                Status = status_messages
                return (Status,)

            elif response.status_code == 422:
                msg = 'Invalid input data'
                status_messages.append(msg)
                self._addError(msg)
                self.Component.Message = msg
                Status = status_messages
                return (Status,)

            elif response.status_code == 500:
                msg = 'Server error - please try again'
                status_messages.append(msg)
                self._addWarning(msg)
                self.Component.Message = msg
                Status = status_messages
                return (Status,)

            else:
                msg = f'Login failed with status code: {response.status_code}'
                status_messages.append(msg)
                self._addError(msg)
                self.Component.Message = msg
                Status = status_messages
                return (Status,)

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server - check URL'
            status_messages.append(msg)
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg
            Status = status_messages
            return (Status,)

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout - server may be slow'
            status_messages.append(msg)
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg
            Status = status_messages
            return (Status,)

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            status_messages.append(msg)
            self._addError(msg)
            self.Component.Message = msg
            Status = status_messages
            return (Status,)

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            status_messages.append(msg)
            self.Component.Message = msg
            Status = status_messages
            return (Status,)
