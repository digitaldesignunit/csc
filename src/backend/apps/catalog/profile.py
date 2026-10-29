#!/usr/bin/env python3.13
"""
The personal profile of an account (decision 8.133): organization, ROR, the
web page of the organization, ORCID and the default role of the actor an account becomes in a record.
Pure functions over plain values: validation and the copy into an actor.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import re
from typing import Any, Dict, Mapping, Optional

ORCID_URL = re.compile(r'^https?://orcid\.org/', re.IGNORECASE)
ROR_URL = re.compile(r'^https?://ror\.org/', re.IGNORECASE)
# 9 characters: a 0, six of Crockford's base32 (no i, l, o, u), two digits
ROR_ID = re.compile(r'^0[a-hj-km-np-tv-z0-9]{6}[0-9]{2}$')
ORCID_ID = re.compile(r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$')

# the actor fields a profile fills when they are empty, and where they come from
PROFILE_TO_ACTOR = {
    'full_name': 'name',
    'organization': 'organization',
    'organization_ror': 'organization_ror',
    'organization_url': 'url',
    'orcid': 'orcid',
}

URL_LIMIT = 500


def orcid_check_digit(digits: str) -> str:
    """The ISO 7064 MOD 11-2 check character of the first 15 digits."""
    total = 0
    for char in digits:
        total = (total + int(char)) * 2
    result = (12 - total % 11) % 11
    return 'X' if result == 10 else str(result)


def normalize_orcid(value: str) -> str:
    """``0000-0002-1825-0097`` from the bare id, the id without hyphens or the
    ``https://orcid.org/...`` form; ValueError when it is none of them or the
    check character is wrong."""
    text = ORCID_URL.sub('', value.strip()).replace(' ', '').upper()
    if re.fullmatch(r'\d{15}[\dX]', text):
        text = '-'.join(text[i:i + 4] for i in range(0, 16, 4))
    if not ORCID_ID.fullmatch(text):
        raise ValueError('an ORCID looks like 0000-0002-1825-0097')
    digits = text.replace('-', '')
    if orcid_check_digit(digits[:15]) != digits[15]:
        raise ValueError('this ORCID has a wrong check digit')
    return text


def normalize_ror(value: str) -> str:
    """``https://ror.org/<id>`` from the bare id or the URL; ValueError when
    the id does not have the form of a ROR id."""
    text = ROR_URL.sub('', value.strip()).strip('/').lower()
    if not ROR_ID.fullmatch(text):
        raise ValueError('a ROR id looks like 03abcde12 (https://ror.org/...)')
    return f'https://ror.org/{text}'


def normalize_url(value: str) -> str:
    """The web page of an organization, trimmed: the check of ``Actor.url``
    (http or https only; ValueError otherwise or over 500 characters)."""
    text = value.strip()
    if not text.lower().startswith(('http://', 'https://')):
        raise ValueError('the website must start with http:// or https://')
    if len(text) > URL_LIMIT:
        raise ValueError(f'at most {URL_LIMIT} characters')
    return text


def clean_text(value: Optional[str], limit: int = 200) -> Optional[str]:
    """Trimmed text, None when empty; ValueError over the limit."""
    text = (value or '').strip()
    if not text:
        return None
    if len(text) > limit:
        raise ValueError(f'at most {limit} characters')
    return text


def fill_actor(actor: Any, profile: Mapping[str, Any]) -> Any:
    """The actor with its empty ``name`` / ``organization`` /
    ``organization_ror`` / ``url`` / ``orcid`` copied from the account's profile (8.133
    e). Typed values win; a redacted actor and an actor that is not an account
    are left as they are. A copy: the profile stays the account's."""
    if not isinstance(actor, dict) or actor.get('kind') != 'user' \
            or not actor.get('user_id') or actor.get('redacted_at'):
        return actor
    filled: Dict[str, Any] = dict(actor)
    for source, target in PROFILE_TO_ACTOR.items():
        if not filled.get(target) and profile.get(source):
            filled[target] = profile[source]
    return filled
