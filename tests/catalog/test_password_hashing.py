"""Password hashing on bcrypt without passlib (0.5.1.0)."""

import bcrypt
import pytest
from pydantic import ValidationError

from apps.catalog.api.auth import get_password_hash, verify_password
from apps.catalog.models import ChangePasswordPayload, RegisterPayload

UMLAUT = '\u00e4'  # a-umlaut: 2 bytes in UTF-8 (escaped to keep the source ASCII)


def test_hash_and_verify_roundtrip():
    hashed = get_password_hash('correct horse battery')
    assert hashed.startswith('$2b$12$')          # same format passlib wrote
    assert verify_password('correct horse battery', hashed)
    assert not verify_password('wrong horse battery', hashed)


def test_hashes_from_before_the_switch_still_verify():
    # passlib on bcrypt < 5 stored plain $2b$ hashes of at most 72 bytes,
    # silently truncating longer (e.g. umlaut-heavy) passwords
    long_password = UMLAUT * 50                     # 100 bytes in UTF-8
    legacy = bcrypt.hashpw(
        long_password.encode('utf-8')[:72], bcrypt.gensalt(4)).decode()
    assert verify_password(long_password, legacy)


def test_malformed_stored_hash_does_not_raise():
    assert not verify_password('anything', 'not-a-bcrypt-hash')


def test_new_passwords_over_72_bytes_are_rejected():
    with pytest.raises(ValidationError):
        RegisterPayload(username='alice', full_name='Alice',
                        email='alice@tu-darmstadt.de', password=UMLAUT * 40)
    with pytest.raises(ValidationError):
        ChangePasswordPayload(current_password='x', new_password=UMLAUT * 40)
    RegisterPayload(username='alice', full_name='Alice',
                    email='alice@tu-darmstadt.de', password=UMLAUT * 36)
