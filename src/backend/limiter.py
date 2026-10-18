"""
Rate limiting: who a request counts for (plan P10 review, decision 8.117 e).

``client_ip`` is the one helper behind every limiter key. A request that
comes from a trusted proxy carries the real client in ``X-Forwarded-For``: the
web server (the Next proxy, behind the Uberspace web proxy) passes it on, and
every proxy appends the address of its peer. Such a header is believed only
when the peer is a trusted proxy (``CSC_TRUSTED_PROXIES``; default: loopback),
and then the client is the rightmost entry that is not a trusted proxy itself:
anything left of it was written by the caller and is never read. The leftmost
entry never is the answer. Without a trusted peer the header is ignored and
the peer address is the client.

``CSC_TRUSTED_PROXIES`` is a comma-separated list of addresses and networks
(``127.0.0.0/8,::1,203.0.113.7``). Loopback is right where the web server
reaches the backend at ``http://127.0.0.1:8000`` (``FASTAPI_URL``); add the
server's own address when it reaches it through the public API host.

Keys: ``limiter`` counts per client address (the login and registration
routes: nobody is signed in yet). ``signed_in_or_ip`` counts a caller with a
valid token per user, others per address (the expensive reads). The token is
checked once per request (``tokens.verified_payload``), here and in the
authentication dependency alike.

Where the counters live: the shared limiter's move from the process to the
store ``CSC_RATE_LIMIT_STORAGE`` names, MongoDB by default (``rate_store.py``,
``use_store``); the local limiter's stay in the process (see "TWO LIMITERS").
"""

import ipaddress
from functools import lru_cache
from typing import Optional, Tuple, Union

from fastapi import Request
from limits.strategies import FixedWindowRateLimiter
from slowapi import Limiter

from rate_store import make_store
from settings import DEFAULT_TRUSTED_PROXIES, get_settings  # noqa: F401
from tokens import verified_payload

TRUSTED_PROXIES_ENV = 'CSC_TRUSTED_PROXIES'

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def parse_address(text: str) -> Optional[IPAddress]:
    """An address as a header or a socket gives it (``1.2.3.4``,
    ``1.2.3.4:5``, ``[::1]:5``, ``::ffff:1.2.3.4``), or None."""
    text = text.strip()
    if text.startswith('['):
        text = text[1:].split(']', 1)[0]
    elif text.count(':') == 1:           # an IPv4 address with a port
        text = text.split(':', 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


@lru_cache(maxsize=8)
def _networks(value: str) -> Tuple[IPNetwork, ...]:
    networks = []
    for item in value.split(','):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError as exc:
            raise ValueError(f'{TRUSTED_PROXIES_ENV}: bad entry {item!r}') \
                from exc
    return tuple(networks)


def trusted_proxies() -> Tuple[IPNetwork, ...]:
    return _networks(get_settings().csc_trusted_proxies
                     or DEFAULT_TRUSTED_PROXIES)


def _is_trusted(address: IPAddress) -> bool:
    return any(address in network for network in trusted_proxies()
               if network.version == address.version)


def client_ip(request: Request) -> str:
    """The address a request counts for."""
    peer_text = request.client.host if request.client else ''
    peer = parse_address(peer_text) if peer_text else None
    if peer is None or not _is_trusted(peer):
        return peer_text or '0.0.0.0'
    chain = [part for value in request.headers.getlist('x-forwarded-for')
             for part in value.split(',') if part.strip()]
    for entry in reversed(chain):
        address = parse_address(entry)
        if address is None:
            break                        # not an address: believe nothing
        if not _is_trusted(address):
            return str(address)
    return str(peer)


def signed_in_or_ip(request: Request) -> str:
    """``user:<id>`` for a caller with a valid token, else the address."""
    header = request.headers.get('authorization') or ''
    scheme, _, token = header.partition(' ')
    if scheme.lower() == 'bearer' and token:
        payload = verified_payload(request, token)
        if payload and payload.get('sub'):
            return f'user:{payload["sub"]}'
    return client_ip(request)


# TWO LIMITERS ----------------------------------------------------------------
# ``shared_limiter`` counts in the store CSC_RATE_LIMIT_STORAGE names (MongoDB
# by default), so that every gunicorn worker counts the same requests. It is
# for the routes where counting across workers is the point: the sign-in, the
# registration, the mails that can be asked for, the password reset and the
# invitation acceptance (the guessing and mail-flooding limits).
# ``local_limiter`` counts in the process. It is for every other limited
# route: the mesh downloads, the catalogue reads, the exports, the public
# GH reads, the test send of a mail template. The ``limits`` MongoDB storage is
# synchronous, so each count it makes blocks the event loop of its worker for a
# database round trip; the high-frequency reads would pay that on every call,
# and they only shed load: a limit per worker, times CSC_WORKERS, is enough.
# The decorator on a route says which it uses; a test pins the shared list
# (tests/api/test_limiter_groups.py). Both start in the process; the API
# moves the shared one to its store when it starts (use_store).
shared_limiter = Limiter(key_func=client_ip, storage_uri='memory://')
local_limiter = Limiter(key_func=client_ip, storage_uri='memory://')


def use_store(settings=None):
    """Count in the store ``CSC_RATE_LIMIT_STORAGE`` names (decision 8.152),
    for the routes and for ``store()``. Called when the API starts, once per
    worker; the connection opens on first use."""
    settings = settings or get_settings()
    new = make_store(settings.rate_limit_uri, settings.mongodb_db)
    shared_limiter._storage = new
    shared_limiter._limiter = FixedWindowRateLimiter(new)
    return new


def store():
    """The store the shared limiter counts in."""
    return shared_limiter._storage
