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
valid token per user, others per address (the expensive reads).
"""

import ipaddress
import os
from functools import lru_cache
from typing import Optional, Tuple, Union

from fastapi import Request
from jose import JWTError, jwt
from slowapi import Limiter

TRUSTED_PROXIES_ENV = 'CSC_TRUSTED_PROXIES'
DEFAULT_TRUSTED_PROXIES = '127.0.0.0/8,::1'

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
    return _networks(os.getenv(TRUSTED_PROXIES_ENV)
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
    state = request.app.state
    if scheme.lower() == 'bearer' and token and \
            getattr(state, 'jwt_secret', None):
        try:
            payload = jwt.decode(
                token, state.jwt_secret, algorithms=[state.jwt_algorithm],
                options={'verify_aud': False})
        except JWTError:
            payload = {}
        if payload.get('sub'):
            return f'user:{payload["sub"]}'
    return client_ip(request)


limiter = Limiter(key_func=client_ip)
