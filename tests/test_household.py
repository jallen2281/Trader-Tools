"""Household sharing: per-record visibility, edit permissions, and what must never leak.

The negative assertions carry most of the weight here. Sharing bugs are silent — an
over-broad filter shows one person another's bank balances and nothing errors.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='hh_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'h.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
TODAY = date.today()


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


with app.app_context():
    db.drop_all()
    db.create_all()
    now = A.datetime.utcnow()
    V = A.CONSENT_VERSION
    db.session.add_all([
        A.User(id=1, google_id='g1', email='jared@x.com', name='Jared', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=2, google_id='g2', email='partner@x.com', name='Partner', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=3, google_id='g3', email='stranger@x.com', name='Stranger', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
    ])
    db.session.flush()
    # Jared: a joint account he'll share, and a private one he won't.
    db.session.add_all([
        A.FinanceAccount(id=10, user_id=1, name='Joint checking', type='checking', balance=5000),
        A.FinanceAccount(id=11, user_id=1, name='Private savings', type='savings', balance=20000),
        A.RecurringBill(id=20, user_id=1, name='Mortgage', category='housing', amount=1900,
                        frequency='monthly', active=True),
        A.SpendTransaction(id=30, user_id=1, posted_at=TODAY.replace(day=min(TODAY.day, 28)),
                           description='Groceries', amount=200, category='food', source='manual'),
        A.PlaidItem(user_id=1, item_id='it-1', access_token_enc=b'x', institution_name='Bank'),
    ])
    db.session.commit()

me, partner, stranger = client_for(1), client_for(2), client_for(3)

print('\n--- before any household exists, nothing is shared ---')
r = partner.get('/api/finance/accounts')
check('partner sees none of my accounts', len(r.get_json()['accounts']) == 0, r.get_json())
r = me.put('/api/household/share/account/10', json={'share_level': 'view'})
check('cannot share without a household', r.status_code == 400, (r.status_code, r.get_json()))

print('\n--- create, invite, accept ---')
r = me.post('/api/household', json={'name': 'Allen household'})
check('create household -> 201', r.status_code == 201, r.status_code)
HID = r.get_json()['id']
r = me.post('/api/household', json={'name': 'Second'})
check('cannot belong to two households', r.status_code == 400, r.status_code)

r = stranger.post('/api/household/%d/invite' % HID, json={'email': 'x@y.com'})
check('a non-member cannot invite', r.status_code == 403, r.status_code)

r = me.post('/api/household/%d/invite' % HID, json={'email': 'PARTNER@x.com',
                                                    'relationship': 'spouse'})
check('invite -> 201', r.status_code == 201, (r.status_code, r.get_json()))
MID = r.get_json()['id']
check('invite matched the existing account', r.get_json()['user_id'] == 2, r.get_json())

r = partner.get('/api/household')
check('partner sees the pending invitation',
      len(r.get_json()['pending_invitations']) == 1, r.get_json())
r = stranger.post('/api/household/invitations/%d' % MID)
check('a stranger cannot accept someone elses invite', r.status_code == 404, r.status_code)

r = partner.get('/api/finance/accounts')
check('an invitation alone shares nothing', len(r.get_json()['accounts']) == 0, r.get_json())

r = partner.post('/api/household/invitations/%d' % MID)
check('accept -> 200', r.status_code == 200, (r.status_code, r.get_json()))
check('membership is active', r.get_json()['status'] == 'active', r.get_json())

print('\n--- membership alone still shares nothing (share_level defaults to none) ---')
r = partner.get('/api/finance/accounts')
check('partner still sees no accounts', len(r.get_json()['accounts']) == 0, r.get_json())
r = partner.get('/api/finance/transactions')
check('and no transactions', r.get_json()['count'] == 0, r.get_json())

print('\n--- share one account for viewing ---')
r = me.put('/api/household/share/account/10', json={'share_level': 'view'})
check('share -> 200', r.status_code == 200, (r.status_code, r.get_json()))
accts = partner.get('/api/finance/accounts').get_json()['accounts']
names = [a['name'] for a in accts]
check('partner now sees the shared account', 'Joint checking' in names, names)
check('but NOT the private one', 'Private savings' not in names, names)
check('stranger still sees nothing',
      len(stranger.get('/api/finance/accounts').get_json()['accounts']) == 0)

print('\n--- view means view: no editing ---')
r = partner.put('/api/finance/accounts/10', json={'balance': 1})
check('partner cannot edit a view-shared account', r.status_code == 404, r.status_code)
with app.app_context():
    check('balance is untouched', db.session.get(A.FinanceAccount, 10).balance == 5000)
r = partner.delete('/api/finance/accounts/10')
check('and cannot delete it', r.status_code == 404, r.status_code)

print('\n--- raise to edit ---')
me.put('/api/household/share/account/10', json={'share_level': 'edit'})
r = partner.put('/api/finance/accounts/10', json={'balance': 5500})
check('partner can now edit', r.status_code == 200, (r.status_code, r.get_json()))
with app.app_context():
    check('the change persisted', db.session.get(A.FinanceAccount, 10).balance == 5500)
r = partner.put('/api/household/share/account/10', json={'share_level': 'none'})
check('but a partner cannot change who else can see it', r.status_code == 404, r.status_code)
with app.app_context():
    check('share level unchanged by the attempt',
          db.session.get(A.FinanceAccount, 10).share_level == 'edit')

print('\n--- shared records roll into household totals ---')
me.put('/api/household/share/bill/20', json={'share_level': 'view'})
me.put('/api/household/share/transaction/30', json={'share_level': 'view'})
bills = partner.get('/api/finance/bills').get_json()
check('shared bill appears for the partner', bills['count'] if 'count' in bills else
      len(bills['bills']), bills)
check('and counts toward the monthly total', bills['total_monthly'] == 1900.0, bills)
txns = partner.get('/api/finance/transactions').get_json()
check('shared transaction is visible', txns['count'] == 1, txns)
ov = partner.get('/api/finance/overview').get_json()
check('household net worth includes the shared account',
      ov['picture']['outlook']['total_assets'] == 5500.0,
      ov['picture']['outlook']['total_assets'])
check('and excludes the private one (would be 25500)',
      ov['picture']['outlook']['total_assets'] != 25500.0)

print('\n--- things that must never be shared ---')
r = me.put('/api/household/share/plaid/1', json={'share_level': 'view'})
check('Plaid items are not shareable at all', r.status_code == 400, (r.status_code, r.get_json()))
r = partner.get('/api/plaid/items')
check('partner sees no Plaid connections', len(r.get_json()['items']) == 0, r.get_json())
with app.app_context():
    mine = A._income_tax_estimate(1)
    theirs = A._income_tax_estimate(2)
check('tax estimates stay per-filer, not pooled',
      theirs['w2_wages'] == 0 and mine['w2_wages'] == 0, (mine['w2_wages'], theirs['w2_wages']))

print('\n--- leaving the household ends visibility ---')
with app.app_context():
    pm = A.HouseholdMember.query.filter_by(household_id=HID, user_id=2).first()
    PMID = pm.id
r = partner.delete('/api/household/members/%d' % PMID)
check('partner can leave', r.status_code == 200, (r.status_code, r.get_json()))
check('and immediately sees nothing',
      len(partner.get('/api/finance/accounts').get_json()['accounts']) == 0)
check('my own records are untouched',
      len(me.get('/api/finance/accounts').get_json()['accounts']) == 2)

print('\n--- purging a member leaves the household intact for the rest ---')
import retention as R  # noqa: E402
with app.app_context():
    m2 = A.HouseholdMember(household_id=HID, user_id=2, role='member', status='active')
    db.session.add(m2)
    db.session.commit()
    owner = db.session.get(A.User, 1)
    R.purge_user_record(db, owner)
    db.session.commit()
    h = db.session.get(A.Household, HID)
    check('household survives its creator being purged', h is not None)
    check('and ownership transferred to the remaining member',
          h is not None and h.created_by == 2, h.created_by if h else None)
    left = A.HouseholdMember.query.filter_by(household_id=HID).all()
    check('only the remaining member is left', len(left) == 1 and left[0].user_id == 2, left)
    check('purged users accounts are gone',
          A.FinanceAccount.query.filter_by(user_id=1).count() == 0)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL HOUSEHOLD CHECKS PASSED')
