"""Plaid integration tests against a scripted fake client — no network, no real keys.

What matters here: the access token is never stored or returned in the clear, Plaid's
amount sign lands correctly in the ledger, income is excluded, sync is incremental and
idempotent, and the whole thing is unreachable without the plaid_link permission.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='plaid_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'p.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

from cryptography.fernet import Fernet          # noqa: E402
KEY = Fernet.generate_key().decode()
os.environ['PLAID_ENCRYPTION_KEY'] = KEY

import app as A                                  # noqa: E402
import plaid_client as pc                        # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
SECRET_TOKEN = 'access-sandbox-DO-NOT-LEAK-abc123'


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def txn(tid, name, amount, primary, detailed='', date='2026-09-02', merchant=None, pending=False):
    return {'transaction_id': tid, 'name': name, 'amount': amount, 'date': date,
            'merchant_name': merchant, 'pending': pending,
            'personal_finance_category': {'primary': primary, 'detailed': detailed}}


class FakePlaid:
    """Scripted Plaid. `pages` is consumed one call at a time by transactions_sync."""
    env = 'sandbox'

    def __init__(self, pages=None, raise_on_sync=None):
        self.pages = list(pages or [])
        self.raise_on_sync = raise_on_sync
        self.calls = []

    def available(self):
        return True

    def link_token_create(self, uid, products, redirect_uri=None, webhook=None, access_token=None):
        self.calls.append(('link_token_create', access_token))
        return {'link_token': 'link-sandbox-tok', 'expiration': '2026-09-05T00:00:00Z'}

    def exchange_public_token(self, public_token):
        self.calls.append(('exchange', public_token))
        return {'access_token': SECRET_TOKEN, 'item_id': 'item-abc'}

    def item_get(self, t):
        return {'item': {'institution_id': 'ins_42'}}

    def institution_get(self, i):
        return {'institution': {'name': 'Test Federal Bank'}}

    def transactions_sync(self, token, cursor=None, count=500):
        self.calls.append(('sync', cursor))
        if self.raise_on_sync:
            raise self.raise_on_sync
        return self.pages.pop(0) if self.pages else {
            'added': [], 'modified': [], 'removed': [], 'next_cursor': cursor, 'has_more': False}

    def accounts_get(self, token):
        self.calls.append(('accounts_get', token))
        return {'accounts': self.accounts}

    def item_remove(self, token):
        self.calls.append(('item_remove', token))
        return {'removed': True}


FakePlaid.accounts = [
    {'account_id': 'acc-chk', 'name': 'Total Checking', 'official_name': 'CHASE TOTAL CHECKING',
     'mask': '1234', 'type': 'depository', 'subtype': 'checking',
     'balances': {'current': 2500.00, 'available': 2450.00, 'limit': None,
                  'iso_currency_code': 'USD'}},
    {'account_id': 'acc-visa', 'name': 'Freedom Visa', 'official_name': 'CHASE FREEDOM',
     'mask': '9876', 'type': 'credit', 'subtype': 'credit card',
     'balances': {'current': 640.25, 'available': 359.75, 'limit': 1000.00,
                  'iso_currency_code': 'USD'}},
]

FAKE = FakePlaid()
A._plaid = lambda: FAKE          # every endpoint resolves the client through this


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
        A.User(id=1, google_id='g1', email='n@x.com', name='NoPerm', role='user',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=2, google_id='g2', email='a@x.com', name='Admin', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
    ])
    db.session.add(A.BudgetCategory(user_id=2, category='food', monthly_limit=400))
    db.session.commit()

noperm, admin = client_for(1), client_for(2)

print('\n--- encryption round-trip ---')
blob = pc.encrypt_token(SECRET_TOKEN)
check('ciphertext does not contain the token', SECRET_TOKEN.encode() not in blob, blob[:40])
check('decrypts back to the original', pc.decrypt_token(blob) == SECRET_TOKEN)
check('encryption_ready() true with a key set', pc.encryption_ready() is True)

print('\n--- permission gate ---')
for method, path in (('GET', '/api/plaid/status'), ('POST', '/api/plaid/link-token'),
                     ('POST', '/api/plaid/exchange'), ('GET', '/api/plaid/items'),
                     ('POST', '/api/plaid/sync')):
    r = noperm.get(path) if method == 'GET' else noperm.post(path, json={})
    ok = r.status_code == 403 and (r.get_json() or {}).get('missing_permission') == 'plaid_link'
    check('%-5s %-26s -> 403 without plaid_link' % (method, path), ok,
          (r.status_code, r.get_json()))

print('\n--- link token refuses to run without an encryption key ---')
saved = os.environ.pop('PLAID_ENCRYPTION_KEY')
r = admin.post('/api/plaid/link-token', json={})
check('no key -> 503, before the user touches Link', r.status_code == 503, r.status_code)
check('explains why', 'PLAID_ENCRYPTION_KEY' in (r.get_json() or {}).get('error', ''))
os.environ['PLAID_ENCRYPTION_KEY'] = saved
r = admin.post('/api/plaid/link-token', json={})
check('key restored -> 200 with a link_token', r.status_code == 200 and r.get_json().get('link_token'),
      (r.status_code, r.get_json()))

print('\n--- exchange stores the item, encrypted ---')
r = admin.post('/api/plaid/exchange', json={'public_token': 'public-sandbox-xyz'})
check('exchange -> 201', r.status_code == 201, (r.status_code, r.get_json()))
body = r.get_json()
check('names the institution', body.get('institution_name') == 'Test Federal Bank', body)
check('response carries no token field', not any('token' in k for k in body), list(body))
check('response body contains no token value', SECRET_TOKEN not in r.get_data(as_text=True))
ITEM_ID = body['id']
with app.app_context():
    it = db.session.get(A.PlaidItem, ITEM_ID)
    check('stored token is ciphertext, not plaintext',
          SECRET_TOKEN.encode() not in bytes(it.access_token_enc), bytes(it.access_token_enc)[:40])
    check('and decrypts back correctly', pc.decrypt_token(it.access_token_enc) == SECRET_TOKEN)

print('\n--- first sync pulls transactions into the ledger ---')
FAKE.pages = [
    {'added': [
        txn('t1', 'WEGMANS #442', 120.55, 'FOOD_AND_DRINK', merchant='Wegmans'),
        txn('t2', 'PAYROLL DIRECT DEP', -2400.00, 'INCOME'),
        txn('t3', 'ACME PROPERTY MGMT', 1800.00, 'RENT_AND_UTILITIES', 'RENT_AND_UTILITIES_RENT'),
        txn('t4', 'DTE ENERGY', 145.20, 'RENT_AND_UTILITIES', 'RENT_AND_UTILITIES_GAS_AND_ELECTRICITY'),
        txn('t5', 'ZZQ UNKNOWN VENDOR', 40.00, 'SOMETHING_NEW'),
     ], 'modified': [], 'removed': [], 'next_cursor': 'cur-1', 'has_more': False},
]
r = admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
res = r.get_json()
check('sync -> 200', r.status_code == 200, (r.status_code, res))
check('added the 4 spend rows', res['added'] == 4, res)
check('skipped the payroll deposit', res['skipped_income'] == 1, res)

with app.app_context():
    rows = {t.external_id: t for t in A.SpendTransaction.query.filter_by(user_id=2).all()}
    check('all rows marked source=plaid', all(t.source == 'plaid' for t in rows.values()))
    check('external_id is plaid:<transaction_id>', 'plaid:t1' in rows, list(rows))
    check('food category from Plaid PFC', rows['plaid:t1'].category == 'food', rows['plaid:t1'].category)
    check('amount sign preserved (positive = money out)', rows['plaid:t1'].amount == 120.55)
    check('RENT detailed -> housing', rows['plaid:t3'].category == 'housing', rows['plaid:t3'].category)
    check('utilities detailed -> utilities', rows['plaid:t4'].category == 'utilities', rows['plaid:t4'].category)
    check('unknown PFC falls back to keyword guess', rows['plaid:t5'].category == 'other',
          rows['plaid:t5'].category)
    check('income never landed in the ledger', 'plaid:t2' not in rows)
    check('merchant carried across', rows['plaid:t1'].merchant == 'Wegmans')
    it = db.session.get(A.PlaidItem, ITEM_ID)
    check('cursor advanced', it.cursor == 'cur-1', it.cursor)
    check('last_synced_at set', it.last_synced_at is not None)

print('\n--- Phase 4 budget rollup sees Plaid spend as actuals ---')
r = admin.get('/api/finance/budgets?month=2026-09')
rowsb = {b['category']: b for b in r.get_json()['budgets']}
check('food actual reflects the synced transaction', rowsb['food']['actual_monthly'] == 120.55,
      rowsb.get('food'))
check('food flagged under its 400 limit', rowsb['food']['over'] is False, rowsb.get('food'))

print('\n--- incremental: modified updates, removed deletes, re-sync is idempotent ---')
FAKE.pages = [
    {'added': [], 'modified': [txn('t1', 'WEGMANS #442', 131.02, 'FOOD_AND_DRINK', merchant='Wegmans')],
     'removed': [{'transaction_id': 't5'}], 'next_cursor': 'cur-2', 'has_more': False},
]
r = admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
res = r.get_json()
check('modified counted as an update, not an insert', res['updated'] == 1 and res['added'] == 0, res)
check('removed counted', res['removed'] == 1, res)
with app.app_context():
    rows = {t.external_id: t for t in A.SpendTransaction.query.filter_by(user_id=2).all()}
    check('amount was updated in place', rows['plaid:t1'].amount == 131.02, rows['plaid:t1'].amount)
    check('removed transaction is gone', 'plaid:t5' not in rows, list(rows))
    check('no duplicate row created', len([k for k in rows if k == 'plaid:t1']) == 1)

FAKE.pages = []          # empty response => nothing changes
r = admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
res = r.get_json()
check('re-sync with no changes imports nothing new',
      {k: res[k] for k in ('added', 'updated', 'removed', 'skipped_income')}
      == {'added': 0, 'updated': 0, 'removed': 0, 'skipped_income': 0}, res)
check('but accounts are still refreshed, since balances move without transactions',
      res['accounts'] == 2, res)

print('\n--- pagination follows has_more ---')
FAKE.pages = [
    {'added': [txn('p1', 'PAGE ONE', 10.0, 'GENERAL_MERCHANDISE')],
     'modified': [], 'removed': [], 'next_cursor': 'c-a', 'has_more': True},
    {'added': [txn('p2', 'PAGE TWO', 20.0, 'GENERAL_MERCHANDISE')],
     'modified': [], 'removed': [], 'next_cursor': 'c-b', 'has_more': False},
]
r = admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
check('both pages consumed in one sync', r.get_json()['added'] == 2, r.get_json())
with app.app_context():
    check('final cursor is the last page cursor',
          db.session.get(A.PlaidItem, ITEM_ID).cursor == 'c-b')

print('\n--- ITEM_LOGIN_REQUIRED becomes its own state, not a generic error ---')
FAKE.raise_on_sync = pc.PlaidError('login required', code='ITEM_LOGIN_REQUIRED')
r = admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
check('sync -> 502', r.status_code == 502, r.status_code)
check('reports status login_required', (r.get_json() or {}).get('status') == 'login_required',
      r.get_json())
with app.app_context():
    check('item marked login_required', db.session.get(A.PlaidItem, ITEM_ID).status == 'login_required')
FAKE.raise_on_sync = None

r = admin.post('/api/plaid/link-token', json={'item_id': ITEM_ID})
check('update-mode link token passes the access_token through',
      any(c[0] == 'link_token_create' and c[1] == SECRET_TOKEN for c in FAKE.calls),
      [c for c in FAKE.calls if c[0] == 'link_token_create'])

print('\n--- disconnect ---')
with app.app_context():
    before = A.SpendTransaction.query.filter_by(user_id=2).count()
r = admin.delete('/api/plaid/items/%d' % ITEM_ID)
res = r.get_json()
check('disconnect -> 200', r.status_code == 200, (r.status_code, res))
check('revoked at Plaid, not just locally', res.get('revoked_at_plaid') is True, res)
check('item/remove was actually called with the token',
      any(c[0] == 'item_remove' and c[1] == SECRET_TOKEN for c in FAKE.calls))
with app.app_context():
    check('stored token row is gone', db.session.get(A.PlaidItem, ITEM_ID) is None)
    check('spending history kept by default',
          A.SpendTransaction.query.filter_by(user_id=2).count() == before, before)

print('\n--- disconnect with ?purge=1 removes the history too ---')
FAKE.pages = [{'added': [txn('z1', 'AGAIN', 5.0, 'FOOD_AND_DRINK')], 'modified': [],
               'removed': [], 'next_cursor': 'z', 'has_more': False}]
admin.post('/api/plaid/exchange', json={'public_token': 'public-sandbox-2'})
with app.app_context():
    iid2 = A.PlaidItem.query.filter_by(user_id=2).first().id
admin.post('/api/plaid/items/%d/sync' % iid2)
r = admin.delete('/api/plaid/items/%d?purge=1' % iid2)
check('purge reports what it deleted', r.get_json().get('transactions_purged', 0) >= 1, r.get_json())
with app.app_context():
    check('no plaid-sourced rows remain',
          A.SpendTransaction.query.filter_by(user_id=2, source='plaid').count() == 0)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PLAID CHECKS PASSED')
