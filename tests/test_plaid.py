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

    def link_token_create(self, uid, products, redirect_uri=None, webhook=None,
                          access_token=None, consented=None):
        self.calls.append(('link_token_create', access_token))
        self.last_consented = list(consented or [])
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

    # The paid products. Empty payloads: this file is about tokens and transactions, and
    # test_plaid_liabilities.py is where their content is exercised. They exist here at
    # all because _plaid_sync_item now calls them whenever the config says they are
    # consented to, and a fake that silently lacks a method the real client has turns a
    # contract change into a confusing failure somewhere else.
    def liabilities_get(self, token, account_ids=None):
        self.calls.append(('liabilities_get', token))
        return {'liabilities': {}}

    def investments_holdings_get(self, token, account_ids=None):
        self.calls.append(('investments_holdings_get', token))
        return {'holdings': [], 'securities': []}


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
check('the endpoint asks for the consented products too, so enabling one later is a '
      'config change rather than six re-authentications',
      FAKE.last_consented == A.Config.PLAID_CONSENTED_PRODUCTS, FAKE.last_consented)
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

print('\n--- a pending paycheck that posts leaves ONE deposit, not two ---')
# The bank sends the pending deposit under one id; when it posts, Plaid removes that id and
# adds the posted one. Only spending used to be deleted on `removed`, so the pending copy
# stayed and the paycheck showed up twice.
FAKE.pages = [{'added': [txn('pend-1', 'GENESEE CHRISTIA PAYROLL', -1881.28, 'INCOME',
                             date='2026-09-10', pending=True)],
               'modified': [], 'removed': [], 'next_cursor': 'cur-p1', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
FAKE.pages = [{'added': [txn('post-1', 'ORIG CO NAME:GENESEE CHRISTIA', -1881.28, 'INCOME',
                             date='2026-09-10')],
               'modified': [], 'removed': [{'transaction_id': 'pend-1'}],
               'next_cursor': 'cur-p2', 'has_more': False}]
res = admin.post('/api/plaid/items/%d/sync' % ITEM_ID).get_json()
with app.app_context():
    paychecks = A.PlaidDeposit.query.filter_by(user_id=2, amount=1881.28).all()
    check('exactly one deposit for the paycheck', len(paychecks) == 1,
          [(p.external_id, p.description) for p in paychecks])
    check('and it is the posted one', paychecks and paychecks[0].external_id == 'plaid:post-1',
          [p.external_id for p in paychecks])
check('the removal is counted', res['removed'] >= 1, res)

print('\n--- a transaction that turns out to be income leaves no spend row behind ---')
# Plaid re-categorises after the fact. Tricia's 2026-08-25 pay arrived first under a
# category that was not INCOME, so it was imported as spending; on a later sync it came
# back in `modified` as INCOME, the deposit was created -- and the original -$1,881.28
# spend row was simply left where it was. The same paycheck then counted once as her
# income and once as $1,881.28 LESS spending, which no report shows as an error.
FAKE.pages = [{'added': [txn('flip-1', 'GENESEE CHRISTIA PAYROLLACH PPD ID: 9807416000',
                             -1881.28, 'GENERAL_SERVICES', date='2026-08-25')],
               'modified': [], 'removed': [], 'next_cursor': 'cur-f1', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
FAKE.pages = [{'added': [], 'modified': [txn('flip-1', 'GENESEE CHRISTIA PAYROLLACH PPD ID: 9807416000',
                                             -1881.28, 'INCOME', date='2026-08-25')],
               'removed': [], 'next_cursor': 'cur-f2', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
with app.app_context():
    spend = A.SpendTransaction.query.filter_by(user_id=2, external_id='plaid:flip-1').first()
    dep = A.PlaidDeposit.query.filter_by(user_id=2, external_id='plaid:flip-1').first()
    check('the paycheck is recorded as a deposit', dep is not None and dep.kind == 'income',
          dep and dep.kind)
    check('and the stale spend row is gone -- not in both tables', spend is None,
          spend and (spend.amount, spend.category))
    check('stored positive, because a deposit of -1881.28 reads as a mistake',
          dep is not None and dep.amount == 1881.28, dep and dep.amount)

print('\n--- an unrecognised credit goes to the arrivals queue, not into spending ---')
# The sign says money came IN. Nothing recognised what it was, so the category resolved to
# 'other' -- and it used to be stored as a negative 'other' spend row, quietly subtracting
# from a total instead of appearing anywhere as a question.
FAKE.pages = [{'added': [txn('cred-1', 'ZZQ MYSTERY CREDIT', -523.40, 'SOMETHING_NEW',
                             date='2026-09-14')],
               'modified': [], 'removed': [], 'next_cursor': 'cur-c1', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
with app.app_context():
    check('not in the spending ledger',
          A.SpendTransaction.query.filter_by(user_id=2, external_id='plaid:cred-1').first() is None)
    d = A.PlaidDeposit.query.filter_by(user_id=2, external_id='plaid:cred-1').first()
    check('recorded as money in', d is not None and d.amount == 523.40, d and d.amount)
    check("and flagged 'unknown' so the arrivals queue asks about it",
          d is not None and d.kind == 'unknown', d and d.kind)

print('\n--- but a refund still nets against the purchase it reverses ---')
# The one credit that genuinely belongs in the spending ledger. A $9.48 Walmart return
# SHOULD reduce 'personal'; routing every credit to the deposits table would have
# overstated spending by every refund ever received.
FAKE.pages = [{'added': [txn('ref-1', 'Walmart', -9.48, 'GENERAL_MERCHANDISE',
                             date='2026-09-15', merchant='Walmart')],
               'modified': [], 'removed': [], 'next_cursor': 'cur-r1', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
with app.app_context():
    t = A.SpendTransaction.query.filter_by(user_id=2, external_id='plaid:ref-1').first()
    check('the refund stays in the ledger', t is not None, t)
    check('against the category it reverses', t is not None and t.category == 'personal',
          t and t.category)
    check('and stays negative, so it reduces that total',
          t is not None and t.amount == -9.48, t and t.amount)
    check('not duplicated into the deposits table',
          A.PlaidDeposit.query.filter_by(user_id=2, external_id='plaid:ref-1').first() is None)

print('\n--- BOTH halves of a card payment stay out of debt ---')
# The real shape of the bug, and the reason the inbound half must be a DEPOSIT rather than
# a negative spend row: _pair_transfers can only pair an outflow against a deposit. While
# the inbound half sat in the spending ledger the pairing never ran, so the outbound half
# stayed in 'debt' -- three "DISCOVER CAP ONE" outflows worth $2,873.51 counted as debt
# service against purchases already counted when the card was used. Both halves are
# genuinely the same movement, and neither is spending.
from datetime import date as _d  # noqa: E402
_dt = _d.today().isoformat()
_pay_out = txn('cap-out', 'DISCOVER CAP ONE', 2766.17, 'LOAN_PAYMENTS', date=_dt)
_pay_out['account_id'] = 'acc-chk'
_pay_in = txn('cap-in', 'CAPITAL ONE ONLINE PYMT', -2766.17, 'LOAN_PAYMENTS', date=_dt)
_pay_in['account_id'] = 'acc-visa'
FAKE.pages = [{'added': [_pay_out, _pay_in], 'modified': [], 'removed': [],
               'next_cursor': 'cur-cap', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
with app.app_context():
    dep = A.PlaidDeposit.query.filter_by(user_id=2, external_id='plaid:cap-in').first()
    out = A.SpendTransaction.query.filter_by(user_id=2, external_id='plaid:cap-out').first()
    check('the inbound half is a deposit, not a negative spend row', dep is not None, dep)
    check("and on a credit card it is a card payment whatever Plaid called it",
          dep is not None and dep.kind == 'card_payment', dep and dep.kind)
    check('the inbound half is NOT in the spending ledger',
          A.SpendTransaction.query.filter_by(user_id=2, external_id='plaid:cap-in').first() is None)
    check('so the outbound half can be paired to it',
          out is not None and dep is not None and out.paired_deposit_id == dep.id,
          (out and out.paired_deposit_id, dep and dep.id))
    check('which takes the outbound half out of debt',
          out is not None and out.category == 'transfer', out and out.category)
    start, end = A._month_bounds(None)
    act = A._spend_actuals(2, start, end)
    check('neither half reaches the debt total', act.get('debt', 0) == 0, act.get('debt'))

print('\n--- the mortgage reaches housing through the real import path ---')
# The test that was missing on 2026-11-05. The keyword rule was verified in isolation and
# in the running pod, and the very next sync still filed $3,103.88 of mortgage into 'other'
# -- because Plaid labels that ACH TRANSFER_OUT, which maps to 'other', which is truthy,
# so the rule was never consulted. A rule the importer cannot reach is not a fix, and only
# a test that goes through the importer would have caught it.
FAKE.pages = [{'added': [txn('mtg-1', 'UWM', 3103.88, 'TRANSFER_OUT', date='2026-11-01'),
                         txn('mtg-2', 'Unitedwholesale Mtg', 3103.88, 'GENERAL_SERVICES',
                             date='2026-12-01'),
                         txn('int-1', 'Interest Charge on Purchases', 789.49, 'BANK_FEES',
                             date='2026-11-02')],
               'modified': [], 'removed': [], 'next_cursor': 'cur-mtg', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
with app.app_context():
    for ext, want, label in (('plaid:mtg-1', 'housing', 'UWM via TRANSFER_OUT'),
                             ('plaid:mtg-2', 'housing', 'Unitedwholesale via GENERAL_SERVICES'),
                             ('plaid:int-1', 'debt', 'interest via BANK_FEES')):
        t = A.SpendTransaction.query.filter_by(user_id=2, external_id=ext).first()
        check('%-38s -> %s' % (label, want),
              t is not None and t.category == want, t and t.category)
    # And the other direction: a specific Plaid category is still trusted over a keyword.
    start, end = A._month_bounds('2026-11')
    act = A._spend_actuals(2, start, end)
    check('the mortgage reaches the housing total, not other',
          act.get('housing', 0) >= 3103.88, act.get('housing'))

print('\n--- a transfer between his own accounts is not a loan payment ---')
# Plaid called "Online Transfer to CHK ...0849" a LOAN_PAYMENT, which maps to 'debt'. That
# is truthy, so the keyword rules were never consulted and $550 of moving money between
# two of his own chequing accounts counted as debt service. A description that names the
# account is now read ahead of Plaid's category.
FAKE.pages = [{'added': [txn('xf-1', 'Online Transfer to CHK ...0849 transaction', 550.00,
                             'LOAN_PAYMENTS', date='2026-08-07'),
                         txn('xf-2', 'PAYPAL INST XFER PPCR CC REPAYME WEB ID: 1234', 2.99,
                             'LOAN_PAYMENTS', date='2026-07-06')],
               'modified': [], 'removed': [], 'next_cursor': 'cur-xf', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
with app.app_context():
    for ext, label in (('plaid:xf-1', 'Online Transfer to CHK'), ('plaid:xf-2', 'INST XFER')):
        t = A.SpendTransaction.query.filter_by(user_id=2, external_id=ext).first()
        check('%-24s is a transfer, not debt' % label,
              t is not None and t.category == 'transfer', t and t.category)

print('\n--- a sync pairs a transfer with its other half ---')
from datetime import date as _date  # noqa: E402
_today = _date.today().isoformat()
_out = txn('xp-out', 'CHASE CARD PMT', 300.00, 'TRANSFER_OUT', date=_today)
_out['account_id'] = 'acc-chk'
_in = txn('xp-in', 'PAYMENT RECEIVED', -300.00, 'TRANSFER_IN', date=_today)
_in['account_id'] = 'acc-visa'
FAKE.pages = [{'added': [_out, _in], 'modified': [], 'removed': [],
               'next_cursor': 'cur-x', 'has_more': False}]
admin.post('/api/plaid/items/%d/sync' % ITEM_ID)
with app.app_context():
    paid = A.SpendTransaction.query.filter_by(user_id=2, external_id='plaid:xp-out').first()
    landed = A.PlaidDeposit.query.filter_by(user_id=2, external_id='plaid:xp-in').first()
    check('the outflow is recorded as a transfer', paid is not None and paid.category == 'transfer',
          paid and paid.category)
    check('paired to the payment that landed on the card',
          paid is not None and landed is not None and paid.paired_deposit_id == landed.id,
          (paid and paid.paired_deposit_id, landed and landed.id))

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
with app.app_context():
    n_accts = A.PlaidAccount.query.filter_by(item_id=ITEM_ID).count()
check('the item being disconnected actually HAS accounts, or the next check proves nothing',
      n_accts > 0, n_accts)
r = admin.delete('/api/plaid/items/%d' % ITEM_ID)
res = r.get_json()
check('disconnect -> 200', r.status_code == 200, (r.status_code, res))
check('revoked at Plaid, not just locally', res.get('revoked_at_plaid') is True, res)
check('item/remove was actually called with the token',
      any(c[0] == 'item_remove' and c[1] == SECRET_TOKEN for c in FAKE.calls))
with app.app_context():
    check('stored token row is gone', db.session.get(A.PlaidItem, ITEM_ID) is None)
    # PlaidAccount.item_id is a NOT NULL foreign key and PlaidItem declared no cascade,
    # so on Postgres this raised ForeignKeyViolation on plaid_accounts_item_id_fkey and
    # NO institution holding an account could be disconnected at all. This suite passed
    # for months regardless, because SQLite does not enforce foreign keys unless it is
    # asked to -- the bug lived in the gap between the test database and the real one.
    check('AND ITS ACCOUNTS GO WITH IT',
          A.PlaidAccount.query.filter_by(item_id=ITEM_ID).count() == 0,
          A.PlaidAccount.query.filter_by(item_id=ITEM_ID).count())
    check('spending history kept by default',
          A.SpendTransaction.query.filter_by(user_id=2).count() == before, before)

print('\n--- ?purge=1 removes THIS connection and no other ---')
# It used to filter on user_id and source='plaid' alone, with nothing naming the item, so
# disconnecting one bank with purge set would have deleted every imported row the user
# had, from every institution. It was unreachable only because the missing delete cascade
# made the endpoint fail first -- fixing that armed it.
#
# Two connections are built by hand here rather than through the fake: FakePlaid returns
# one fixed set of account_ids, and _sync_plaid_accounts upserts on account_id, so a
# second sync would re-point the SAME account rows at the new item instead of giving it
# its own. Which is a real hazard in its own right, just not the one under test.
with app.app_context():
    import plaid_client as _pc
    keep = A.PlaidItem(user_id=2, item_id='item-keep', institution_name='Keep Bank',
                       status='active', access_token_enc=_pc.encrypt_token('tok-keep'))
    drop = A.PlaidItem(user_id=2, item_id='item-drop', institution_name='Drop Bank',
                       status='active', access_token_enc=_pc.encrypt_token('tok-drop'))
    db.session.add_all([keep, drop])
    db.session.commit()
    db.session.add_all([
        A.PlaidAccount(user_id=2, item_id=keep.id, account_id='acct-keep', mask='1111'),
        A.PlaidAccount(user_id=2, item_id=drop.id, account_id='acct-drop', mask='2222'),
    ])
    db.session.add_all([
        A.SpendTransaction(user_id=2, source='plaid', external_id='plaid:keep-1',
                           plaid_account_id='acct-keep', description='KEEP ME',
                           amount=11.0, posted_at=A.date(2026, 10, 1), category='food'),
        A.SpendTransaction(user_id=2, source='plaid', external_id='plaid:drop-1',
                           plaid_account_id='acct-drop', description='DROP ME',
                           amount=22.0, posted_at=A.date(2026, 10, 2), category='food'),
    ])
    db.session.add_all([
        A.PlaidDeposit(user_id=2, external_id='dep:keep-1', plaid_account_id='acct-keep',
                       description='KEEP PAY', amount=100.0,
                       posted_at=A.date(2026, 10, 1)),
        A.PlaidDeposit(user_id=2, external_id='dep:drop-1', plaid_account_id='acct-drop',
                       description='DROP PAY', amount=200.0,
                       posted_at=A.date(2026, 10, 2)),
    ])
    db.session.commit()
    keep_id, drop_id = keep.id, drop.id

r = admin.delete('/api/plaid/items/%d?purge=1' % drop_id)
body = r.get_json()
check('purge -> 200', r.status_code == 200, (r.status_code, body))
check('it reports one transaction purged, not every row in the ledger',
      body.get('transactions_purged') == 1, body)
check('and one deposit, because phantom income from a bank that is gone is no better',
      body.get('deposits_purged') == 1, body)
with app.app_context():
    check('the disconnected connection is gone', db.session.get(A.PlaidItem, drop_id) is None)
    check('ITS row is gone',
          A.SpendTransaction.query.filter_by(user_id=2,
                                             external_id='plaid:drop-1').count() == 0)
    check('THE OTHER BANK IS UNTOUCHED -- this is the whole point',
          A.SpendTransaction.query.filter_by(user_id=2,
                                             external_id='plaid:keep-1').count() == 1)
    check('and so is its deposit',
          A.PlaidDeposit.query.filter_by(user_id=2, external_id='dep:keep-1').count() == 1)
    check('the surviving connection is still connected',
          db.session.get(A.PlaidItem, keep_id) is not None)
    check('and still has its account',
          A.PlaidAccount.query.filter_by(item_id=keep_id).count() == 1)


print('\n--- a failure records the CODE, not only the sentence ---')
# Five sites in app.py and one in the sync job stored str(e) and dropped e.code, so
# nothing downstream could tell a connection update mode would repair from one that was
# gone. The UI fell back to testing status == 'login_required' and offered no way out of
# any other failure -- which is how a healthy connection came to be re-linked from
# scratch, duplicating the ledger.
with app.app_context():
    it = A.PlaidItem(user_id=2, item_id='item-rec', institution_name='Recovery Bank',
                     status='active', access_token_enc=pc.encrypt_token('tok-rec'))
    db.session.add(it)
    db.session.commit()
    rid = it.id

    A._record_item_error(it, pc.PlaidError('log in again', code='ITEM_LOGIN_REQUIRED'))
    db.session.commit()
    check('login_required becomes its own status', it.status == 'login_required', it.status)
    check('and the code is kept', it.last_error_code == 'ITEM_LOGIN_REQUIRED',
          it.last_error_code)
    check('along with the message', 'log in again' in (it.last_error or ''), it.last_error)
    check('recovery says update mode', it.recovery() == 'reconnect', it.recovery())
    check('and to_dict carries both out to the UI',
          it.to_dict().get('recovery') == 'reconnect'
          and it.to_dict().get('last_error_code') == 'ITEM_LOGIN_REQUIRED', it.to_dict())

    A._record_item_error(it, pc.PlaidError('gone', code='ITEM_NOT_FOUND'))
    db.session.commit()
    check('a removed Item is a generic error, not login_required',
          it.status == 'error', it.status)
    check('AND RECOVERY SAYS A NEW CONNECTION, not update mode -- there is no Item left '
          'to repair', it.recovery() == 'relink', it.recovery())

    A._record_item_error(it, pc.PlaidError('consent', code='ADDITIONAL_CONSENT_REQUIRED'))
    db.session.commit()
    check('a missing consent scope is repaired in update mode',
          it.recovery() == 'reconnect', it.recovery())

    A._record_item_error(it, pc.PlaidError('down', code='INSTITUTION_DOWN'))
    db.session.commit()
    check('a transient outage offers nothing to click', it.recovery() is None, it.recovery())
    A._record_item_error(it, pc.PlaidError('???', code='SOME_CODE_I_HAVE_NEVER_SEEN'))
    db.session.commit()
    check('nor does an unrecognised code -- it is not guessed at',
          it.recovery() is None, it.recovery())
    A._record_item_error(it, pc.PlaidError('no code at all'))
    db.session.commit()
    check('an error with no code stores None rather than the string "None"',
          it.last_error_code is None, repr(it.last_error_code))

    print('\n--- a healthy connection has nothing to recover from ---')
    it.status = 'active'
    it.last_error = it.last_error_code = None
    db.session.commit()
    check('recovery is None when active', it.recovery() is None, it.recovery())
    it.last_error_code = 'ITEM_LOGIN_REQUIRED'
    check('and stays None even with a stale code left on an active row',
          it.recovery() is None, it.recovery())

    print('\n--- a row written before the column existed still works ---')
    it.status = 'login_required'
    it.last_error_code = None
    db.session.commit()
    check('login_required with no code falls back to update mode',
          it.recovery() == 'reconnect', it.recovery())
    it.status = 'error'
    check('but a bare "error" with no code promises nothing',
          it.recovery() is None, it.recovery())

    print('\n--- recovering clears the code, so no stale reason lingers ---')
    A._record_item_error(it, pc.PlaidError('x', code='ITEM_LOGIN_REQUIRED'))
    db.session.commit()
    r = admin.post('/api/plaid/items/%d/sync' % rid)
    with app.app_context():
        it2 = db.session.get(A.PlaidItem, rid)
        check('a successful sync clears the status', it2.status == 'active',
              (it2.status, r.status_code))
        check('the message', it2.last_error is None, it2.last_error)
        check('and the code', it2.last_error_code is None, it2.last_error_code)


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PLAID CHECKS PASSED')
