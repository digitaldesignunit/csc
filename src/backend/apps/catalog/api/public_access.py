#!/usr/bin/env python3.13

import hashlib
from typing import Any, Dict, Optional

from apps.catalog.models import User


def identity_allows_anonymous_read(identity_doc: Dict[str, Any]) -> bool:
    return identity_doc.get('is_public') is True


def public_cache_control() -> str:
    return 'public, max-age=3600'


def viewer_etag(etag: str, user: Optional[User]) -> str:
    """What an anonymous caller may see of the people differs from what a
    signed-in one sees (8.101): the representation has its own ETag, so a 304
    never hands one tier's body to the other."""
    if user is not None:
        return etag
    return hashlib.sha256(f'{etag}::anonymous'.encode('utf-8')).hexdigest()


def viewer_headers(*, anonymous_public: bool = False,
                   etag: Optional[str] = None,
                   cache_control: Optional[str] = None) -> Dict[str, str]:
    """The headers of a response whose body depends on who asks: the cache
    rule, the ETag, and ``Vary: Authorization`` so that a cache does not hand
    an answer to a caller with another token (or none). A 304 carries them
    too."""
    headers = {
        'Cache-Control': cache_control or (
            public_cache_control() if anonymous_public
            else 'private, max-age=3600'),
        'Vary': 'Authorization',
    }
    if etag:
        headers['ETag'] = etag
    return headers
