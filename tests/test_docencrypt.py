"""Encryption at rest for stored tax documents.

The load-bearing assertion is that the SSN never appears in the stored bytes — that is the
whole exposure, since the Ceph volumes underneath are unencrypted and the backups are taken
from this same table.
"""
import io as _io
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='docenc_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'd.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

from cryptography.fernet import Fernet   # noqa: E402
KEY = Fernet.generate_key().decode()
os.environ['DOC_ENCRYPTION_KEY'] = KEY

import app as A            # noqa: E402
import doc_crypto          # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
SSN = b'%PDF-1.4 Employee SSN 123-45-6789 wages 150000'


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


with app.app_context():
    db.drop_all()
    db.create_all()
    now = A.datetime.utcnow()
    db.session.add(A.User(id=1, google_id='g1', email='d@x.com', name='D', role='admin',
                          privacy_consent_at=now, privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

print('\n--- round trip ---')
blob = doc_crypto.encrypt_document(SSN)
check('ciphertext does not contain the SSN', b'123-45-6789' not in blob, blob[:40])
check('nor any plaintext from the file', b'Employee' not in blob)
check('decrypts back exactly', doc_crypto.decrypt_document(blob) == SSN)
check('encryption_ready() true with a key', doc_crypto.encryption_ready() is True)

print('\n--- upload stores ciphertext, never plaintext ---')
r = c.post('/api/tax/documents',
           data={'file': (_io.BytesIO(SSN), 'w2.pdf'), 'doc_type': 'W2'},
           content_type='multipart/form-data')
check('upload -> 201', r.status_code == 201, (r.status_code, r.get_data()[:160]))
did = r.get_json()['id']
with app.app_context():
    doc = db.session.get(A.TaxDocument, did)
    check('row is marked encrypted', doc.data_encrypted is True, doc.data_encrypted)
    check('STORED BYTES DO NOT CONTAIN THE SSN', b'123-45-6789' not in bytes(doc.data),
          bytes(doc.data)[:60])
    check('stored size records the plaintext length', doc.size == len(SSN), doc.size)

print('\n--- and nothing in the whole database dump contains it ---')
with app.app_context():
    raw = db.session.execute(db.text('SELECT data FROM tax_documents')).fetchall()
    joined = b''.join(bytes(r[0]) for r in raw if r[0] is not None)
check('a table-wide scan finds no SSN (this is what a backup would hold)',
      b'123-45-6789' not in joined)

print('\n--- download still serves the real file ---')
r = c.get('/api/tax/documents/%d/download' % did)
check('200', r.status_code == 200, r.status_code)
check('bytes match the original exactly', r.get_data() == SSN, r.get_data()[:60])
check('still served as a PDF', r.headers['Content-Type'].startswith('application/pdf'))

print('\n--- legacy plaintext rows keep working during the backfill ---')
with app.app_context():
    db.session.add(A.TaxDocument(id=99, user_id=1, doc_type='1099', filename='old.pdf',
                                 content_type='application/pdf', data=SSN,
                                 data_encrypted=False, size=len(SSN)))
    db.session.commit()
r = c.get('/api/tax/documents/99/download')
check('a pre-encryption document still downloads', r.status_code == 200 and r.get_data() == SSN,
      r.status_code)

print('\n--- the backfill converts them, idempotently ---')
r = c.post('/api/tax/documents/encrypt-existing', json={})
check('backfill -> 200', r.status_code == 200, (r.status_code, r.get_json()))
check('reports one converted', r.get_json().get('encrypted') == 1, r.get_json())
with app.app_context():
    doc = db.session.get(A.TaxDocument, 99)
    check('legacy row is now encrypted', doc.data_encrypted is True)
    check('and its bytes no longer contain the SSN', b'123-45-6789' not in bytes(doc.data))
r = c.get('/api/tax/documents/99/download')
check('it still downloads correctly afterwards', r.get_data() == SSN)
r = c.post('/api/tax/documents/encrypt-existing', json={})
check('running it again converts nothing', r.get_json().get('encrypted') == 0, r.get_json())

print('\n--- without a key, uploads are refused rather than stored in the clear ---')
saved = os.environ.pop('DOC_ENCRYPTION_KEY')
check('encryption_ready() false', doc_crypto.encryption_ready() is False)
r = c.post('/api/tax/documents',
           data={'file': (_io.BytesIO(SSN), 'x.pdf'), 'doc_type': 'W2'},
           content_type='multipart/form-data')
check('upload refused with 503', r.status_code == 503, (r.status_code, r.get_data()[:120]))
check('and names the missing key', 'DOC_ENCRYPTION_KEY' in r.get_data(as_text=True))
with app.app_context():
    check('nothing was written', A.TaxDocument.query.filter_by(filename='x.pdf').count() == 0)
os.environ['DOC_ENCRYPTION_KEY'] = saved

print('\n--- a wrong key fails loudly rather than serving garbage ---')
os.environ['DOC_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
r = c.get('/api/tax/documents/%d/download' % did)
check('download errors instead of returning corrupt bytes', r.status_code == 500, r.status_code)
check('and explains that the key is probably wrong',
      'differs from the key' in r.get_data(as_text=True), r.get_data(as_text=True)[:160])
os.environ['DOC_ENCRYPTION_KEY'] = KEY
check('restoring the right key recovers the document',
      c.get('/api/tax/documents/%d/download' % did).get_data() == SSN)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL DOCUMENT ENCRYPTION CHECKS PASSED')
