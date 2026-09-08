"""Serving user-uploaded document bytes safely.

Uploads are already type-checked, so this is defence in depth: the download path must not
trust content_type from the database, because a row can predate that check or arrive by
another route, and these bytes are served from the app's own origin.
"""
import io as _io
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='docsec_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'd.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []


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
    db.session.flush()
    db.session.add_all([
        # A normal receipt.
        A.TaxDocument(id=1, user_id=1, doc_type='receipt', filename='receipt.pdf',
                      content_type='application/pdf', data=b'%PDF-1.4 hello'),
        # A row whose type was never validated — predates the upload check, or was written
        # directly. This is the case the download path has to defend against.
        A.TaxDocument(id=2, user_id=1, doc_type='receipt', filename='evil.html',
                      content_type='text/html',
                      data=b'<script>alert(document.cookie)</script>'),
        # SVG executes script in a browser and is not in the allowlist.
        A.TaxDocument(id=3, user_id=1, doc_type='receipt', filename='x.svg',
                      content_type='image/svg+xml', data=b'<svg onload="alert(1)"/>'),
        # A filename that would break out of the quoted header value.
        A.TaxDocument(id=4, user_id=1, doc_type='receipt', filename='a"; x=1\r\nX-Evil: y',
                      content_type='application/pdf', data=b'%PDF-1.4'),
    ])
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

print('\n--- uploads are validated at the door ---')
r = c.post('/api/tax/documents',
           data={'file': (_io.BytesIO(b'<script>x</script>'), 'e.html'), 'doc_type': 'receipt'},
           content_type='multipart/form-data')
check('an HTML upload is rejected outright', r.status_code == 400, (r.status_code, r.get_data()[:120]))
check('and says why', 'unsupported type' in r.get_data(as_text=True), r.get_data(as_text=True)[:120])

print('\n--- a legitimate PDF still renders inline ---')
r = c.get('/api/tax/documents/1/download')
check('200', r.status_code == 200, r.status_code)
check('served as application/pdf', r.headers['Content-Type'].startswith('application/pdf'),
      r.headers.get('Content-Type'))
check('inline, so it previews in the browser',
      r.headers['Content-Disposition'].startswith('inline'), r.headers.get('Content-Disposition'))
check('nosniff set', r.headers.get('X-Content-Type-Options') == 'nosniff', dict(r.headers))
check('CSP set', 'default-src' in (r.headers.get('Content-Security-Policy') or ''),
      r.headers.get('Content-Security-Policy'))

print('\n--- an untrusted type is never rendered ---')
for did, label in ((2, 'text/html'), (3, 'image/svg+xml')):
    r = c.get('/api/tax/documents/%d/download' % did)
    check('%s -> served as application/octet-stream' % label,
          r.headers['Content-Type'].startswith('application/octet-stream'),
          r.headers.get('Content-Type'))
    check('%s -> attachment, not inline' % label,
          r.headers['Content-Disposition'].startswith('attachment'),
          r.headers.get('Content-Disposition'))
    check('%s -> nosniff prevents the browser overriding that' % label,
          r.headers.get('X-Content-Type-Options') == 'nosniff')
    check('%s -> bytes are unchanged (still downloadable)' % label, len(r.get_data()) > 0)

print('\n--- the filename cannot inject a header ---')
r = c.get('/api/tax/documents/4/download')
cd = r.headers.get('Content-Disposition', '')
check('no raw quote survives into the header', cd.count('"') == 2, cd)
check('no CR/LF in the header', '\r' not in cd and '\n' not in cd, repr(cd))
check('no injected header appeared', 'X-Evil' not in dict(r.headers), sorted(dict(r.headers)))

print('\n--- still owner-scoped ---')
with app.app_context():
    db.session.add(A.User(id=2, google_id='g2', email='o@x.com', name='O',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()
other = app.test_client()
with other.session_transaction() as sess:
    sess['_user_id'] = '2'
    sess['_fresh'] = True
check('another user cannot download it', other.get('/api/tax/documents/1/download').status_code == 404)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL DOCUMENT SECURITY CHECKS PASSED')
