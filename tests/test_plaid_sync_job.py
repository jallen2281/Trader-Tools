"""The scheduled sync, and specifically how it fails.

A sync that stops working quietly leaves exactly the stale ledger the job exists to
prevent, while the application looks perfectly healthy. That is not hypothetical: the feed
reached 12 days stale with all six institutions reporting `active` and no error anywhere,
and the visible damage was four bills reading PAST DUE when only one of them was.

So the two kinds of failure are different on purpose, and this file is here to keep them
that way:

  * ITEM_LOGIN_REQUIRED cannot be retried -- a human has to re-authenticate -- so the run
    exits 0 and the signal goes where a human will see it: onto the item, and into the
    notification feed, ONCE.
  * anything else might succeed next time, so the run exits non-zero and lets the Job's
    backoffLimit and failedJobsHistoryLimit do their work.

A job that exits non-zero on a dead connection would be red forever and teach you to
ignore it; a job that announces the same dead connection every six hours is its own kind
of silence. Both failure modes are the same bug as a stale ledger, one level up.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='syncjob_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'j.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
# The job sets this itself; set it here too so importing app.py in a test does not start
# the alert monitor and leave a thread ticking for the rest of the run.
os.environ['TT_BACKGROUND_JOBS'] = '0'
sys.path.insert(0, os.getcwd())

from cryptography.fernet import Fernet            # noqa: E402
os.environ['PLAID_ENCRYPTION_KEY'] = Fernet.generate_key().decode()

import app as A                                    # noqa: E402
import plaid_client as pc                          # noqa: E402
import plaid_sync_job as job                       # noqa: E402

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
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    for iid, name in ((1, 'Chase'), (2, 'American Express'), (3, 'SoFi')):
        db.session.add(A.PlaidItem(id=iid, user_id=1, item_id='item-%d' % iid,
                                   institution_name=name, status='active',
                                   access_token_enc=pc.encrypt_token('access-tok-%d' % iid)))
    db.session.commit()


# What _plaid_sync_item should do for each institution, keyed by name. Patched onto the
# app module because run_sync imports it at call time.
BEHAVIOUR = {}
CALLS = []


def fake_sync(item):
    CALLS.append(item.institution_name)
    b = BEHAVIOUR.get(item.institution_name, 'ok')
    if isinstance(b, Exception):
        raise b
    return {'added': 3, 'updated': 1, 'removed': 0, 'skipped_income': 2}


A._plaid_sync_item = fake_sync


def notes():
    return A.Notification.query.filter_by(user_id=1, category='system').all()


print('\n--- the happy path totals every institution ---')
with app.app_context():
    BEHAVIOUR.clear()
    r = job.run_sync(db)
    check('all three synced', r['synced'] == 3, r)
    check('counts are summed, not overwritten', r['added'] == 9 and r['skipped_income'] == 6, r)
    check('nothing needs re-auth', r['reauth'] == [], r['reauth'])
    check('nothing failed', r['failed'] == [], r['failed'])
    check('and no notification was raised for a healthy run', not notes(), len(notes()))

print('\n--- a bank asking for re-authentication is announced, once ---')
with app.app_context():
    BEHAVIOUR['American Express'] = pc.PlaidError('login required',
                                                  code='ITEM_LOGIN_REQUIRED')
    r = job.run_sync(db)
    item = db.session.get(A.PlaidItem, 2)
    check('the item records the state Link needs', item.status == 'login_required', item.status)
    check('and why', bool(item.last_error), item.last_error)
    check('it is reported as re-auth, not as a failure',
          r['reauth'] == ['American Express'] and r['failed'] == [], (r['reauth'], r['failed']))
    check('exactly one notification was raised', len(notes()) == 1,
          [n.title for n in notes()])
    n = notes()[0]
    check('it names the institution', 'American Express' in (n.title or ''), n.title)
    check('it is high priority -- the ledger silently stops updating',
          n.priority == 'high', n.priority)
    check('it says what goes stale', 'stale' in (n.message or '').lower(), n.message)
    check('the other two still synced -- one bank does not stop the rest',
          r['synced'] == 2, r)

with app.app_context():
    before = len(notes())
    r = job.run_sync(db)
    check('a second run does NOT announce the same dead connection again',
          len(notes()) == before, (before, len(notes())))
    check('but it is still reported every run', r['reauth'] == ['American Express'], r['reauth'])
    check('and nothing new was announced', r['announced'] == 0, r['announced'])

print('\n--- reconnecting clears the state, and can be announced again later ---')
with app.app_context():
    BEHAVIOUR.pop('American Express')
    r = job.run_sync(db)
    item = db.session.get(A.PlaidItem, 2)
    check('a successful sync clears the stale status', item.status == 'active', item.status)
    check('and clears the error with it', item.last_error is None, item.last_error)
    BEHAVIOUR['American Express'] = pc.PlaidError('login required again',
                                                  code='ITEM_LOGIN_REQUIRED')
    was = len(notes())
    job.run_sync(db)
    check('a NEW failure after a recovery is announced again', len(notes()) == was + 1,
          (was, len(notes())))
    BEHAVIOUR.pop('American Express')

print('\n--- an ordinary error is retryable, and says so by exit code ---')
with app.app_context():
    BEHAVIOUR['SoFi'] = pc.PlaidError('upstream 503', code='INTERNAL_SERVER_ERROR')
    r = job.run_sync(db)
    item = db.session.get(A.PlaidItem, 3)
    check("the item is 'error', not 'login_required'", item.status == 'error', item.status)
    check('it is reported as a failure', len(r['failed']) == 1, r['failed'])
    check('the code is carried through for whoever reads the log',
          r['failed'][0].get('code') == 'INTERNAL_SERVER_ERROR', r['failed'][0])
    check('no notification -- a transient 503 is not the user\'s problem to fix',
          r['announced'] == 0, r['announced'])

print('\n--- a bug in our own code fails loudly rather than silently ---')
with app.app_context():
    BEHAVIOUR.clear()
    BEHAVIOUR['Chase'] = ValueError('something unexpected')
    r = job.run_sync(db)
    check('an unexpected exception is caught per institution', len(r['failed']) == 1, r['failed'])
    check('the type is preserved in the report',
          'ValueError' in r['failed'][0].get('error', ''), r['failed'][0])
    check('and the other institutions still synced', r['synced'] == 2, r)

print('\n--- exit codes: the whole point of the design ---')
with app.app_context():
    BEHAVIOUR.clear()
    check('a clean run exits 0', job.main() == 0)
    BEHAVIOUR['American Express'] = pc.PlaidError('login required',
                                                  code='ITEM_LOGIN_REQUIRED')
    check('re-auth exits 0 -- retrying cannot fix it, and a red Job forever is ignored',
          job.main() == 0)
    BEHAVIOUR.clear()
    BEHAVIOUR['SoFi'] = pc.PlaidError('upstream 503', code='INTERNAL_SERVER_ERROR')
    check('a retryable failure exits non-zero so the Job goes red', job.main() == 1)
    BEHAVIOUR.clear()

print('\n--- it targets one user when told to ---')
with app.app_context():
    db.session.add(A.User(id=2, google_id='g2', email='two@x.com', name='Two', role='user',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.PlaidItem(id=9, user_id=2, item_id='item-9', institution_name='Citi',
                               status='active',
                               access_token_enc=pc.encrypt_token('access-tok-9')))
    db.session.commit()
    CALLS.clear()
    r = job.run_sync(db, user_id=2)
    check('only that user\'s items are synced', CALLS == ['Citi'], CALLS)
    check('and it is counted', r['items'] == 1 and r['synced'] == 1, r)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PLAID SYNC JOB CHECKS PASSED')
