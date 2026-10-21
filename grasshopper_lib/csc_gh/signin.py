"""Sign in Grasshopper without a password (decision 8.168 f).

The Session component signs in through the OAuth server of the backend, the way
Claude Code and ``gh auth login --web`` do: the authorization code flow with
PKCE (S256) and a loopback redirect. SignIn starts a listener on ``127.0.0.1``
on a random free port, opens the browser at ``/authorize`` for the fixed public
client ``csc-grasshopper`` with the redirect ``http://127.0.0.1:<port>/callback``
and scope ``gh:client``; the user allows on the consent page of the website; the
browser returns to the listener with the code (and the ``state`` this module
made); the code is exchanged at ``/token``. The access token is the normal CSC
JWT of an hour, the refresh token (``csc_dev_...``) is good 30 days after its
last use, is replaced on every use and is kept on this computer for this Windows
user only: encrypted with DPAPI, in a file under ``%APPDATA%\\DDU_CSC``, one
entry per server address, never in a document and never in an input or output.

This module is pure Python 3.9 (standard library only; the HTTP calls go
through a ``post`` function the caller gives, the browser through an
``open_browser`` function). It holds what is worth a test: the URLs and forms,
PKCE and the state check, the callback listener, the storage format, DPAPI
(``ctypes``) and the order of the ways to sign in. The component keeps only the
glue to Grasshopper.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

CLIENT_ID = 'csc-grasshopper'
SCOPE = 'gh:client'
CALLBACK_PATH = '/callback'
LOOPBACK = '127.0.0.1'
LISTEN_SECONDS = 600          # the browser has this long to come back
COMPUTER_MAX = 60
STORE_VERSION = 1
STORE_NAME = 'signin.json'

NO_SIGN_IN_TEXT = 'Press SignIn (Windows) or connect Username and Password'
WINDOWS_ONLY_TEXT = ('The sign-in without a password is Windows only: connect '
                     'Username and Password')
DONE_PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
             '<title>Signed in</title></head><body><p>Signed in, you can '
             'close this tab.</p></body></html>')
FAILED_PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
               '<title>Not signed in</title></head><body><p>The sign-in was '
               'not completed. You can close this tab and press SignIn '
               'again.</p></body></html>')


class SignInError(Exception):
    """A sign-in step failed; ``str(error)`` is the sentence for the user.
    ``dead`` is True when the server says the refresh token is no longer good
    (``invalid_grant``): the stored sign-in is of no use any more."""

    def __init__(self, message, dead=False):
        super().__init__(message)
        self.dead = dead


# ADDRESSES, PKCE, STATE ---------------------------------------------------------
def normalise_server(url):
    """A server address as the key of its stored sign-in: lower-case scheme and
    host, no default port, no trailing slash."""
    text = (url or '').strip()
    parts = urlsplit(text)
    scheme = (parts.scheme or 'https').lower()
    host = (parts.hostname or '').lower()
    if not host:
        return text.rstrip('/').lower()
    if ':' in host:
        host = '[%s]' % host
    port = parts.port
    if port and not ((scheme == 'https' and port == 443)
                     or (scheme == 'http' and port == 80)):
        host = '%s:%d' % (host, port)
    return '%s://%s%s' % (scheme, host, parts.path.rstrip('/'))


def new_verifier():
    """A PKCE code verifier (RFC 7636: 43 to 128 url-safe characters)."""
    return secrets.token_urlsafe(48)


def challenge_of(verifier):
    """The S256 code challenge of a verifier."""
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')


def new_state():
    return secrets.token_urlsafe(24)


def redirect_uri(port):
    return 'http://%s:%d%s' % (LOOPBACK, port, CALLBACK_PATH)


def computer_name(raw=None):
    """The name of this computer, as short printable text without markup (the
    server shows it on the consent page and in the list, as text nobody
    checked)."""
    name = socket.gethostname() if raw is None else raw
    text = ''.join(ch for ch in str(name or '') if ch.isprintable()
                   and ch not in '<>"\'&\\')
    return ' '.join(text.split())[:COMPUTER_MAX]


def authorize_url(server, challenge, state, port, computer=None):
    """Where the browser goes to ask for the sign-in."""
    query = [('response_type', 'code'), ('client_id', CLIENT_ID),
             ('redirect_uri', redirect_uri(port)), ('scope', SCOPE),
             ('state', state), ('code_challenge', challenge),
             ('code_challenge_method', 'S256')]
    if computer:
        query.append(('computer', computer))
    return '%s/authorize?%s' % (server.rstrip('/'), urlencode(query))


def check_callback(query, state):
    """The code of a callback (a dict of the query values, first of each), or
    ``SignInError``. The state must be the one this sign-in made."""
    if query.get('state') != state:
        raise SignInError('The answer did not belong to this sign-in (state '
                          'differs).')
    if query.get('error'):
        if query['error'] == 'access_denied':
            raise SignInError('The sign-in was denied in the browser.')
        raise SignInError('The sign-in was refused: %s.' % query['error'])
    code = query.get('code')
    if not code:
        raise SignInError('The answer carried no code.')
    return code


# THE FORMS OF THE TOKEN ENDPOINT -------------------------------------------------
def code_form(code, verifier, port):
    return {'grant_type': 'authorization_code', 'code': code,
            'redirect_uri': redirect_uri(port), 'client_id': CLIENT_ID,
            'code_verifier': verifier}


def refresh_form(refresh_token):
    return {'grant_type': 'refresh_token', 'refresh_token': refresh_token,
            'client_id': CLIENT_ID}


def revoke_form(refresh_token):
    # the SDK's revocation endpoint wants the field even for a public client
    return {'token': refresh_token, 'client_id': CLIENT_ID,
            'client_secret': ''}


class TokenSet(object):
    """What ``/token`` gave: the JWT, the new refresh token, seconds."""

    def __init__(self, access_token, refresh_token, expires_in):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in


def _detail(response):
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def parse_token_answer(response):
    """A ``TokenSet`` from the answer of ``/token``, or ``SignInError``."""
    status = response.status_code
    body = _detail(response)
    if status == 200 and body.get('access_token') \
            and body.get('refresh_token'):
        try:
            seconds = int(body.get('expires_in') or 3600)
        except (TypeError, ValueError):
            seconds = 3600
        return TokenSet(body['access_token'], body['refresh_token'], seconds)
    if status == 400 and body.get('error') == 'invalid_grant':
        raise SignInError('The sign-in is no longer valid (expired, revoked '
                          'or used twice): press SignIn again.', dead=True)
    if status == 429:
        raise SignInError('The server asks to wait a moment (too many '
                          'sign-ins): try again in a minute.')
    text = body.get('error_description') or body.get('detail') \
        or body.get('error') or 'status %s' % status
    raise SignInError('The server did not give a token: %s' % text)


def exchange_code(post, server, code, verifier, port, headers=None):
    """Buy the tokens with the code (``post(url, data, headers, timeout)``)."""
    answer = post('%s/token' % server.rstrip('/'),
                  code_form(code, verifier, port), _form_headers(headers), 20)
    return parse_token_answer(answer)


def refresh_access(post, server, refresh_token, headers=None):
    """A new JWT and a new refresh token for the stored one. ``SignInError``
    with ``dead`` set when the server will not take it any more."""
    answer = post('%s/token' % server.rstrip('/'),
                  refresh_form(refresh_token), _form_headers(headers), 30)
    return parse_token_answer(answer)


def revoke_refresh(post, server, refresh_token, headers=None):
    """End the sign-in on the server; True when the server answered 200."""
    answer = post('%s/revoke' % server.rstrip('/'),
                  revoke_form(refresh_token), _form_headers(headers), 20)
    return answer.status_code == 200


def _form_headers(headers):
    out = {'Content-Type': 'application/x-www-form-urlencoded'}
    out.update(headers or {})
    return out


# THE ORDER OF THE WAYS TO SIGN IN ---------------------------------------------------
def choose_sign_in(username, password, has_stored, windows):
    """``'password'``, ``'stored'`` or ``'none'``: connected Username and
    Password win (the current path, also the way on macOS); else the stored
    sign-in of this server (Windows only); else nothing."""
    if (username or '').strip() and (password or '').strip():
        return 'password'
    if has_stored and windows:
        return 'stored'
    return 'none'


def none_text(windows):
    return NO_SIGN_IN_TEXT if windows else WINDOWS_ONLY_TEXT


# THE LISTENER -------------------------------------------------------------------------
class CallbackListener(object):
    """One request on ``http://127.0.0.1:<port>/callback``, then closed.

    ``start`` binds a random free port on 127.0.0.1 only and serves in a
    background thread for at most ``timeout`` seconds. A request is accepted
    only for GET ``/callback``, with ``Host`` ``127.0.0.1:<port>`` (no DNS
    rebinding) and the expected ``state``; anything else gets a 400/404 and the
    listener keeps waiting. The first accepted request ends it: its answer is a
    plain page without script. ``wait`` gives ``('code', value)``,
    ``('error', text)`` or ``('timeout', None)``.
    """

    def __init__(self, state, timeout=LISTEN_SECONDS):
        self.state = state
        self.timeout = timeout
        self.port = None
        self._result = None
        self._done = threading.Event()
        self._server = None
        self._thread = None

    def start(self):
        listener = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'
            server_version = 'CSC-signin'

            def log_message(self, *args):
                pass

            def _reply(self, status, page=None):
                body = (page or '').encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy',
                                 "default-src 'none'")
                self.send_header('Connection', 'close')
                self.end_headers()
                if body and self.command != 'HEAD':
                    self.wfile.write(body)

            def do_GET(self):
                parts = urlsplit(self.path)
                expected = '%s:%d' % (LOOPBACK, listener.port)
                if self.headers.get('Host') != expected:
                    return self._reply(400)
                if parts.path != CALLBACK_PATH:
                    return self._reply(404)
                query = {k: v[0] for k, v in parse_qs(parts.query).items()}
                if query.get('state') != listener.state:
                    return self._reply(400)
                try:
                    listener._result = ('code', check_callback(
                        query, listener.state))
                    page = DONE_PAGE
                except SignInError as error:
                    listener._result = ('error', str(error))
                    page = FAILED_PAGE
                self._reply(200, page)
                listener._done.set()

            def do_POST(self):
                self._reply(405)

            do_PUT = do_DELETE = do_PATCH = do_POST

        self._server = http.server.HTTPServer((LOOPBACK, 0), Handler)
        self._server.timeout = 0.25
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._serve, name='csc-signin-listener', daemon=True)
        self._thread.start()
        return self.port

    def _serve(self):
        deadline = time.time() + self.timeout
        try:
            while not self._done.is_set() and time.time() < deadline:
                self._server.handle_request()
        finally:
            if self._result is None:
                self._result = ('timeout', None)
            self._done.set()
            try:
                self._server.server_close()
            except Exception:
                pass

    def wait(self, timeout=None):
        self._done.wait(timeout)
        return self._result

    def close(self):
        """Stop listening now (a sign-in that was cancelled)."""
        if self._result is None:
            self._result = ('timeout', None)
        self._done.set()
        if self._thread is not None:
            self._thread.join(2)


# ONE SIGN-IN IN PROGRESS --------------------------------------------------------------
class SignInFlow(object):
    """SignIn, from the button to the tokens, off the UI thread.

    ``start`` binds the listener, opens the browser and returns at once; a
    background thread waits for the browser, checks the state, exchanges the
    code and calls ``on_done`` (the component asks Grasshopper to solve it
    again). ``state`` is ``waiting``, ``done`` or ``failed``; ``tokens`` or
    ``error`` hold the result. ``post(url, data, headers, timeout)`` and
    ``open_browser(url)`` are given by the caller.
    """

    def __init__(self, server, post, open_browser, on_done=None,
                 computer=None, headers=None, timeout=LISTEN_SECONDS):
        self.server = server
        self._post = post
        self._open = open_browser
        self._on_done = on_done
        self.computer = computer_name() if computer is None else computer
        self.headers = headers or {}
        self.timeout = timeout
        self.state = 'idle'
        self.tokens = None
        self.error = None
        self.started = None
        self.url = None
        self._listener = None
        self._verifier = new_verifier()
        self._state = new_state()

    def start(self):
        self._listener = CallbackListener(self._state, self.timeout)
        port = self._listener.start()
        self.url = authorize_url(self.server, challenge_of(self._verifier),
                                 self._state, port, self.computer)
        self.state = 'waiting'
        self.started = time.time()
        threading.Thread(target=self._run, args=(port,),
                         name='csc-signin', daemon=True).start()
        try:
            self._open(self.url)
        except Exception as error:
            self._finish(error='The browser could not be opened (%s): open '
                         'this address yourself: %s' % (error, self.url))
        return self.url

    def seconds_left(self):
        if self.state != 'waiting' or self.started is None:
            return 0
        return max(0, int(self.started + self.timeout - time.time()))

    def cancel(self):
        if self._listener is not None:
            self._listener.close()

    def _run(self, port):
        kind, value = self._listener.wait()
        if self.state != 'waiting':
            return
        if kind == 'timeout':
            return self._finish(error='No answer from the browser in %d '
                                'minutes: press SignIn again.'
                                % (self.timeout // 60))
        if kind == 'error':
            return self._finish(error=value)
        try:
            tokens = exchange_code(self._post, self.server, value,
                                   self._verifier, port, self.headers)
        except SignInError as error:
            return self._finish(error=str(error))
        except Exception as error:      # a network error: the sentence
            return self._finish(error='The sign-in could not be completed '
                                '(%s).' % error)
        self._finish(tokens=tokens)

    def _finish(self, tokens=None, error=None):
        if self.state in ('done', 'failed'):
            return
        self.tokens, self.error = tokens, error
        self.state = 'done' if tokens is not None else 'failed'
        if self._on_done is not None:
            try:
                self._on_done()
            except Exception:
                pass


# THE STORED SIGN-IN -------------------------------------------------------------------
def store_path(environ=None, windows=None):
    """``%APPDATA%\\DDU_CSC\\signin.json`` (the folder of the catalog cache)."""
    environ = os.environ if environ is None else environ
    if (os.name == 'nt') if windows is None else windows:
        base = environ.get('APPDATA', '')
    else:
        base = os.path.join(os.path.expanduser('~'), 'Library',
                            'Application Support')
    return os.path.join(base, 'DDU_CSC', STORE_NAME)


def _read(path):
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {'version': STORE_VERSION, 'entries': {}}
    if not isinstance(data, dict) or not isinstance(data.get('entries'), dict):
        return {'version': STORE_VERSION, 'entries': {}}
    return data


def _write(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temporary = '%s.%d.tmp' % (path, os.getpid())
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
    os.replace(temporary, path)


def has_entry(path, server):
    return normalise_server(server) in _read(path)['entries']


def save_entry(path, server, refresh_token, protect, computer=None, now=None):
    """Keep the refresh token of ``server``, encrypted by ``protect`` (DPAPI).
    A renewed token replaces the old one."""
    data = _read(path)
    blob = protect(refresh_token.encode('ascii'))
    data['version'] = STORE_VERSION
    data['entries'][normalise_server(server)] = {
        'blob': base64.b64encode(blob).decode('ascii'),
        'saved': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                               time.gmtime(time.time() if now is None
                                           else now)),
        'computer': computer or ''}
    _write(path, data)


def load_entry(path, server, unprotect):
    """The refresh token stored for ``server``, or None (no entry, a file that
    cannot be read, or an entry another Windows user wrote)."""
    entry = _read(path)['entries'].get(normalise_server(server))
    if not isinstance(entry, dict):
        return None
    try:
        blob = base64.b64decode(entry['blob'].encode('ascii'))
        return unprotect(blob).decode('ascii')
    except Exception:
        return None


def delete_entry(path, server):
    """Remove the entry of ``server``; True when there was one."""
    data = _read(path)
    removed = data['entries'].pop(normalise_server(server), None) is not None
    if removed:
        _write(path, data)
    return removed


# DPAPI -----------------------------------------------------------------------------------
_ENTROPY = b'DDU_CSC sign-in'


def _blob_class():
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_char))]
    return Blob


def _dpapi(function_name, data, flags_name):
    """CryptProtectData / CryptUnprotectData through ctypes: the current
    Windows user's key, no user interface. ctypes is part of Python, so this
    does not depend on the .NET assemblies Rhino loads."""
    if os.name != 'nt':
        raise SignInError('DPAPI exists on Windows only.')
    import ctypes
    from ctypes import wintypes
    blob_type = _blob_class()
    # use_last_error: the error code is kept per thread right after the call,
    # so the text below never reports a stale one
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    function = getattr(crypt32, function_name)
    function.argtypes = [
        ctypes.POINTER(blob_type), wintypes.LPCWSTR if function_name ==
        'CryptProtectData' else ctypes.c_void_p, ctypes.POINTER(blob_type),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(blob_type)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source = ctypes.create_string_buffer(data, len(data))
    entropy = ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
    blob_in = blob_type(len(data), ctypes.cast(source, ctypes.POINTER(
        ctypes.c_char)))
    blob_entropy = blob_type(len(_ENTROPY), ctypes.cast(
        entropy, ctypes.POINTER(ctypes.c_char)))
    blob_out = blob_type()
    ui_forbidden = 0x1
    description = 'CSC sign-in' if function_name == 'CryptProtectData' \
        else None
    ok = function(ctypes.byref(blob_in), description,
                  ctypes.byref(blob_entropy), None, None, ui_forbidden,
                  ctypes.byref(blob_out))
    if not ok:
        raise SignInError('Windows could not %s the sign-in (error %d).'
                          % (flags_name, ctypes.get_last_error()))
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def dpapi_protect(data):
    """Encrypt bytes for the current Windows user (DPAPI)."""
    return _dpapi('CryptProtectData', data, 'protect')


def dpapi_unprotect(blob):
    """Decrypt what ``dpapi_protect`` made, for the same Windows user."""
    return _dpapi('CryptUnprotectData', blob, 'unprotect')
