"""Verify the privacy policy page and the consent gate against a throwaway SQLite DB."""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='consent_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'c.db').replace('\\', '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']

sys.path.insert(0, os.getcwd())
import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db = A.db
UID = 1
fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='c-test', email='c@example.com', name='Consent Test'))
    db.session.commit()

anon = app.test_client()

print('\n--- privacy policy is public ---')
r = anon.get('/privacy')
check('GET /privacy anonymously -> 200', r.status_code == 200, r.status_code)
body = r.get_data(as_text=True)
check('page renders the policy heading', 'Privacy Policy' in body)
check('discloses AI document transmission', 'Anthropic' in body)
check('discloses SSN-bearing documents', 'Social Security' in body)
check('links Plaid end user policy', 'plaid.com/legal' in body)
check('publishes a real contact address', 'admin@kegbot.net' in body)
check('no unfilled placeholders remain', '[YOUR' not in body and '[EFFECTIVE' not in body, body[:0])

check('footer links to the terms', '/terms' in body)

print('\n--- public landing page (Google OAuth verification requirement) ---')
import re as _re   # sentences wrap across indented source lines; normalize before matching
r = anon.get('/')
check('GET / anonymously -> 200, not a redirect', r.status_code == 200,
      (r.status_code, r.headers.get('Location')))
lbody = r.get_data(as_text=True)
check('describes what the app does', 'budgeting' in lbody and 'portfolio' in lbody.lower())
check('links the privacy policy from the home page', '/privacy' in lbody)
check('links the terms from the home page', '/terms' in lbody)
check('offers a sign-in entry point', '/login' in lbody)
check('states what Google data is used for', 'identify your account' in lbody)
check('states no Gmail/Drive/Calendar access', 'Gmail' in lbody)
check('carries the not-advice disclaimer', 'not financial, investment, tax, or legal advice'
      in _re.sub(r'\s+', ' ', lbody))
check('references the logo asset', 'logo-256.png' in lbody or 'logo-128.png' in lbody)

print('\n--- terms of service is public ---')
r = anon.get('/terms')
check('GET /terms anonymously -> 200', r.status_code == 200, r.status_code)
tbody = r.get_data(as_text=True)
import re as _re
flat = _re.sub(r'\s+', ' ', tbody)   # the sentence wraps across indented source lines
check('disclaims financial advice',
      'Nothing this application produces is financial, investment, tax, or legal advice' in flat,
      [x for x in flat.split('.') if 'legal advice' in x][:1])
check('warns AI output can be wrong', 'can be wrong' in tbody)
check('covers copy trading risk', 'copy trading' in tbody.lower())
check('covers paper trading not being real', 'Simulated' in tbody)
check('has a limitation of liability', 'Limitation of liability' in tbody)
check('links back to the privacy policy', '/privacy' in tbody)
check('names a governing jurisdiction', 'State of Michigan' in flat, tbody[:0])
check('terms carry no unfilled placeholders', '[YOUR' not in tbody and '[EFFECTIVE' not in tbody)

print('\n--- signed in, consent not yet given ---')
c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = str(UID)
    sess['_fresh'] = True

r = c.get('/finances')
check('page request redirects to /consent', r.status_code == 302 and '/consent' in r.headers.get('Location', ''),
      (r.status_code, r.headers.get('Location')))

r = c.get('/api/finance/transactions')
check('API request -> 403 (not a redirect)', r.status_code == 403, r.status_code)
check('403 carries machine-readable code', (r.get_json() or {}).get('code') == 'consent_required', r.get_json())

r = c.get('/consent')
check('GET /consent renders', r.status_code == 200, r.status_code)
cbody = r.get_data(as_text=True)
check('consent page names the AI processing', 'Anthropic' in cbody)
check('consent page offers a decline path', '/logout' in cbody)
check('consent covers the terms of service, not just privacy', '/terms' in cbody, cbody[:0])
check('checkbox text says "agree to the Terms"',
      'agree to the' in _re.sub(r'\s+', ' ', cbody) and 'Terms of' in cbody)
check('consent page shows the version', A.CONSENT_VERSION in cbody, A.CONSENT_VERSION)
check('app chrome uses the new logo, not the robot svg',
      'logo-64.png' in cbody and 'robot-icon.svg' not in cbody)

r = c.get('/privacy')
check('/privacy still reachable without consent', r.status_code == 200, r.status_code)
r = c.get('/terms')
check('/terms still reachable without consent', r.status_code == 200, r.status_code)
r = c.get('/logout')
check('/logout reachable without consent (decline works)', r.status_code in (200, 302), r.status_code)

print('\n--- submitting consent ---')
c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = str(UID)
    sess['_fresh'] = True

r = c.post('/consent', data={})
check('POST without ticking the box -> 400', r.status_code == 400, r.status_code)
with app.app_context():
    u = db.session.get(A.User, UID)
    check('no consent recorded on refusal', u.privacy_consent_version is None, u.privacy_consent_version)

r = c.post('/consent', data={'accept': '1'})
check('POST with acceptance -> redirect', r.status_code == 302, r.status_code)
with app.app_context():
    u = db.session.get(A.User, UID)
    check('consent version recorded', u.privacy_consent_version == A.CONSENT_VERSION, u.privacy_consent_version)
    check('consent timestamp recorded', u.privacy_consent_at is not None)

print('\n--- after consent ---')
r = c.get('/api/finance/transactions')
check('API now passes the gate', r.status_code == 200, r.status_code)

print('\n--- version bump re-prompts ---')
original = A.CONSENT_VERSION
A.CONSENT_VERSION = '2099-01-01'
r = c.get('/api/finance/transactions')
check('bumping the policy version re-gates an already-consented user', r.status_code == 403, r.status_code)
A.CONSENT_VERSION = original
r = c.get('/api/finance/transactions')
check('restoring the version lets them back through', r.status_code == 200, r.status_code)

print('\n--- anonymous users are not gated into a redirect loop ---')
r = anon.get('/finances')
check('anonymous hits login, not consent',
      r.status_code == 302 and '/consent' not in r.headers.get('Location', ''),
      r.headers.get('Location'))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL CONSENT + PRIVACY CHECKS PASSED')
