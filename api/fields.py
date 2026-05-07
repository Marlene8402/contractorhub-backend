"""Custom model fields.

EncryptedTextField — wraps Django's TextField with Fernet symmetric
encryption at rest. Used for QB OAuth tokens (and the QBWC password
when it ships) so a Postgres dump doesn't hand attackers every
customer's QuickBooks. Decryption happens transparently on read;
encryption on write.

Uses a separate env var FIELD_ENCRYPTION_KEY so it can be rotated
independently of Django's SECRET_KEY (rotating SECRET_KEY shouldn't
require re-encrypting every QB token).

In production, FIELD_ENCRYPTION_KEY must be set or imports fail —
silent fallback would silently corrupt data. In DEBUG dev, we
auto-derive a stable key from SECRET_KEY so local testing works
without extra env setup, accepting that local data isn't truly
secret.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.checks import Warning, register
from django.db import models


@register(deploy=True)
def field_encryption_key_set(app_configs, **kwargs):
    """Deploy-time check: warn if FIELD_ENCRYPTION_KEY isn't set in
    production. Raised as a `manage.py check --deploy` warning, which
    shows up in Railway's build logs without bricking the deploy."""
    errors = []
    if not getattr(settings, 'DEBUG', False) and not getattr(settings, 'FIELD_ENCRYPTION_KEY', ''):
        errors.append(Warning(
            "FIELD_ENCRYPTION_KEY is not set; QB tokens will be encrypted "
            "with a key derived from SECRET_KEY, coupling their rotation. "
            "Set FIELD_ENCRYPTION_KEY to an explicit Fernet key for "
            "independent rotation.",
            hint="Generate with: python -c 'from cryptography.fernet "
                 "import Fernet; print(Fernet.generate_key().decode())'",
            id='security.W090',
        ))
    return errors


def _get_fernet() -> Fernet:
    """Resolve the Fernet key from settings. Cached on the function via
    closure so we don't re-derive every read/write.

    If FIELD_ENCRYPTION_KEY is not set, falls back to a key derived from
    SECRET_KEY. This keeps tests and local dev working without extra env
    setup. A separate Django system check (security.E090) warns when
    running in production without an explicit FIELD_ENCRYPTION_KEY, so
    deployers see the gap at `manage.py check --deploy` time without
    crashing the worker on first request.
    """
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', '') or ''
    if not key:
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


_fernet = None


def _fernet_cached() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = _get_fernet()
    return _fernet


class EncryptedTextField(models.TextField):
    """TextField encrypted at rest. Reads return plaintext, writes
    encrypt before storage. NULL/empty stays NULL/empty (no encryption).

    Storage size: Fernet adds ~100 bytes overhead + 33% base64 inflation
    on top of the plaintext. Fine for OAuth tokens (typically <1KB).
    """
    description = "Symmetrically-encrypted text"

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        try:
            return _fernet_cached().decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            # Either the row was written with a different key, OR
            # this is unencrypted legacy data from before migration.
            # Returning the raw value lets the migration encrypt it
            # forward without crashing every read.
            return value

    def to_python(self, value):
        # Already plaintext (e.g., assigned in code, or from a form)
        return value

    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        if isinstance(value, str):
            value = value.encode()
        return _fernet_cached().encrypt(value).decode()
