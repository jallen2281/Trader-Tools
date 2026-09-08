"""Verify paid-AI endpoints are gated on the 'ai_analysis' permission."""
import io as _io
import os
import subprocess
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='aigate_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'a.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

# Document uploads now require an encryption key — without one the app refuses to store a
# file rather than writing Social Security numbers to disk in the clear.
from cryptography.fernet import Fernet  # noqa: E402
os.environ['DOC_ENCRYPTION_KEY'] = Fernet.generate_key().decode()

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []

PAID = [
    ('GET', '/api/tax/ai-read'),
    ('POST', '/api/finance/ai-read'),
    ('POST', '/api/sop/ai-review'),
    ('POST', '/api/sop/generate'),
    ('GET', '/api/correlation/ai-read'),
    ('GET', '/api/ai/status?test=1'),
]


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def client_for(uid):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    return c


def call(c, method, path):
    return c.get(path) if method == 'GET' else c.post(path, json={})


with app.app_context():
    db.drop_all()
    db.create_all()
    V = A.CONSENT_VERSION
    now = A.datetime.utcnow()
    # 1 = plain registered user (no groups), 2 = admin, 3 = member of an ai_analysis group
    db.session.add_all([
        A.User(id=1, google_id='g1', email='p@x.com', name='Plain', role='user',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=2, google_id='g2', email='a@x.com', name='Admin', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=3, google_id='g3', email='m@x.com', name='Member', role='user',
               privacy_consent_at=now, privacy_consent_version=V),
    ])
    g = A.Group(name='AI', description='', permissions=['ai_analysis'])
    db.session.add(g)
    db.session.flush()
    member = db.session.get(A.User, 3)   # keep a reference; SQLAlchemy needs the parent alive
    member.groups.append(g)
    db.session.commit()

print('\n--- permission registry ---')
check("'plaid_link' is registered", 'plaid_link' in A.PERMISSIONS, list(A.PERMISSIONS))
check("'ai_analysis' is registered", 'ai_analysis' in A.PERMISSIONS)

print('\n--- a newly registered user (no groups) cannot spend the API key ---')
c1 = client_for(1)
with app.app_context():
    check('plain user has zero effective permissions',
          A._effective_permissions(db.session.get(A.User, 1)) == set())
for method, path in PAID:
    r = call(c1, method, path)
    ok = r.status_code == 403 and (r.get_json() or {}).get('missing_permission') == 'ai_analysis'
    check('%-5s %-32s -> 403' % (method, path), ok, (r.status_code, r.get_json()))

print('\n--- the free diagnostic stays open ---')
r = c1.get('/api/ai/status')
check('/api/ai/status without ?test=1 -> 200', r.status_code == 200, r.status_code)
check('still reports engine booleans', 'claude' in (r.get_json() or {}), r.get_json())

print('\n--- admin bypasses (operator must not lock themself out) ---')
c2 = client_for(2)
for method, path in PAID:
    r = call(c2, method, path)
    check('%-5s %-32s not 403 for admin' % (method, path), r.status_code != 403,
          (r.status_code, r.get_json()))

print('\n--- a granted group passes the gate ---')
c3 = client_for(3)
with app.app_context():
    check('member resolves ai_analysis',
          'ai_analysis' in A._effective_permissions(db.session.get(A.User, 3)))
for method, path in PAID:
    r = call(c3, method, path)
    check('%-5s %-32s not 403 for granted user' % (method, path), r.status_code != 403,
          (r.status_code, r.get_json()))

print('\n--- upload still works without AI permission (doc stored, just not read) ---')
data = {'file': (_io.BytesIO(b'%PDF-1.4 fake receipt'), 'r.pdf'), 'doc_type': 'receipt'}
r = c1.post('/api/tax/documents', data=data, content_type='multipart/form-data')
check('upload accepted for ungated user', r.status_code == 201, (r.status_code, r.get_data()[:160]))
with app.app_context():
    docs = A.TaxDocument.query.filter_by(user_id=1).all()
    check('document was stored', len(docs) == 1, len(docs))
    check('no AI extraction was attempted', not (docs[0].extracted or {}) if docs else False,
          docs[0].extracted if docs else None)
r = c1.post('/api/tax/documents/%d/extract' % docs[0].id)
check('explicit extract endpoint is gated', r.status_code == 403, r.status_code)

print('\n--- SECRET_KEY guard (subprocess) ---')
# db_config calls load_dotenv(), which finds the repo .env and repopulates SECRET_KEY, so
# unsetting the variable cannot reach the condition here. Setting it explicitly to the dev
# literal does, and is the realistic failure anyway: someone pastes the template value.
probe = os.path.join(TMP, 'probe.py')
_io.open(probe, 'w', encoding='utf-8').write(
    'import os, sys\n'
    'sys.path.insert(0, %r)\n'
    'try:\n'
    '    import db_config\n'
    '    print("NO_RAISE:" + db_config.DatabaseConfig.SECRET_KEY)\n'
    'except RuntimeError as e:\n'
    '    print("RAISED:" + str(e)[:60])\n' % os.getcwd()
)


def probe_with(secret, flask_env):
    env = dict(os.environ)
    env['SECRET_KEY'] = secret
    env['FLASK_ENV'] = flask_env
    return subprocess.run([sys.executable, probe], capture_output=True, text=True,
                          env=env, cwd=os.getcwd()).stdout.strip()


out = probe_with('dev-secret-key-change-in-production', 'production')
check('production + dev key -> refuses to boot', out.startswith('RAISED:'), out[:120])

out = probe_with('dev-secret-key-change-in-production', 'development')
check('development + dev key -> boots fine', out.startswith('NO_RAISE:'), out[:120])

out = probe_with('a-real-production-secret-value', 'production')
check('production + real key -> boots fine', out.startswith('NO_RAISE:'), out[:120])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL AI-GATE CHECKS PASSED')
