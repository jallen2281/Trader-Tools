"""Encryption at rest for stored tax documents.

These files are the most sensitive thing the application holds: W-2 and 1099 forms carry
Social Security numbers, employer details and full wage figures, and they sit in the
database as raw bytes. The storage layer underneath them is unencrypted MicroCeph, and the
hardware lives in a colocation facility where staff can physically reach the drives — so
disk-level protection is not available and would not, on its own, cover the nightly
database dumps anyway.

Encrypting the bytes in the application covers all three exposures at once: the live
database, every backup taken from it, and any disk that leaves the building.

The key is DELIBERATELY separate from PLAID_ENCRYPTION_KEY. The two have very different
rotation consequences — rotating the Plaid key costs users a reconnect, while rotating this
one makes every stored document permanently unreadable unless they are re-encrypted first.
Tying them together would mean the cheap rotation could never be performed without the
expensive one.
"""
import logging
import os

logger = logging.getLogger(__name__)

ENV_KEY = 'DOC_ENCRYPTION_KEY'


class DocumentCryptoError(RuntimeError):
    """Raised when a document cannot be encrypted or decrypted."""


def _fernet():
    from cryptography.fernet import Fernet
    key = os.getenv(ENV_KEY, '')
    if not key:
        raise DocumentCryptoError(
            '%s is not set. Uploaded tax documents contain Social Security numbers and are '
            'only ever stored encrypted, so uploads are refused without it. Generate a key '
            'with: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"' % ENV_KEY)
    return Fernet(key.encode() if isinstance(key, str) else key)


def encryption_ready():
    """Whether documents can be encrypted, without raising — for status and upload checks."""
    try:
        _fernet()
        return True
    except Exception:
        return False


def encrypt_document(raw: bytes) -> bytes:
    if raw is None:
        return None
    return _fernet().encrypt(bytes(raw))


def decrypt_document(blob: bytes) -> bytes:
    if blob is None:
        return None
    try:
        return _fernet().decrypt(bytes(blob))
    except DocumentCryptoError:
        raise
    except Exception as e:
        # A wrong or rotated key looks exactly like corruption from here. Say which it
        # probably is, because the recovery differs completely.
        raise DocumentCryptoError(
            'Could not decrypt a stored document. The most likely cause is that %s differs '
            'from the key it was encrypted with; restoring the original key recovers it, '
            'whereas re-encrypting with a new one does not. (%s)' % (ENV_KEY, e))


def document_bytes(doc) -> bytes:
    """Plaintext bytes for a TaxDocument, whichever format it is stored in.

    Rows written before encryption existed have data_encrypted false and are returned as
    they are, so the feature keeps working during the backfill rather than breaking every
    historical document the moment it ships.
    """
    if doc is None or doc.data is None:
        return None
    if getattr(doc, 'data_encrypted', False):
        return decrypt_document(doc.data)
    return bytes(doc.data)


def encrypt_existing(db, TaxDocument, user_id=None, batch=200):
    """Backfill: encrypt documents still stored in the clear.

    Idempotent and resumable — it only touches rows with data_encrypted false, so it can be
    run repeatedly and interrupted safely. Commits per batch so a failure part-way leaves
    the already-converted rows converted rather than rolling everything back.
    """
    if not encryption_ready():
        raise DocumentCryptoError('%s is not set; cannot encrypt existing documents.' % ENV_KEY)
    q = TaxDocument.query.filter(
        db.or_(TaxDocument.data_encrypted.is_(False), TaxDocument.data_encrypted.is_(None)),
        TaxDocument.data.isnot(None))
    if user_id is not None:
        q = q.filter(TaxDocument.user_id == user_id)

    converted = failed = 0
    pending = 0
    for doc in q.all():
        try:
            doc.data = encrypt_document(bytes(doc.data))
            doc.data_encrypted = True
            converted += 1
            pending += 1
            if pending >= batch:
                db.session.commit()
                pending = 0
        except Exception as e:
            db.session.rollback()
            pending = 0
            failed += 1
            logger.error('encrypt_existing: document %s failed: %s', getattr(doc, 'id', '?'), e)
    if pending:
        db.session.commit()
    logger.info('encrypt_existing: %d document(s) encrypted, %d failed', converted, failed)
    return {'encrypted': converted, 'failed': failed}
