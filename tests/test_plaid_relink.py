"""Connecting a bank you have already connected.

This is written from an incident, not a hypothesis. SoFi needed consent for liabilities --
a healthy connection, just not authorised for a product -- and the only control the UI
offered was "+ Connect a bank". That made a SECOND connection, and three things broke
quietly at once:

  * 48 transactions were imported again. Dedupe keys on external_id =
    plaid:<transaction_id> and **Plaid's transaction ids are per Item**, so the same
    purchase arrives under a different id and the guard cannot see it. $49,154.07 of
    phantom spending, zero genuinely new rows.
  * Both connections' accounts ended up feeding the same records, and
    _apply_plaid_balance SUMS every account pointing at a record (which is correct for
    SoFi's vaults). Assets overstated by $31,785.34.
  * Neither connection could then be deleted, because PlaidAccount.item_id is a NOT NULL
    foreign key and PlaidItem declared no cascade.

So: refuse the second connection while the first one works, and point at update mode,
which keeps the history. Where the first one is genuinely GONE from Plaid -- ITEM_NOT_FOUND
cannot be repaired in update mode -- let the replacement through and carry the records
across, because otherwise the user re-links every account by hand while their balances are
fed by nothing.

Adoption only does what is deterministic: an id swap. Duplicate ROWS are reported and
never deleted, because the rule that finds them is right for pointing a person at a list
and much too loose to act on alone.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='relink_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'r.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
os.environ['TT_BACKGROUND_JOBS'] = '0'
sys.path.insert(0, os.getcwd())

from cryptography.fernet import Fernet            # noqa: E402
os.environ['PLAID_ENCRYPTION_KEY'] = Fernet.generate_key().decode()

from datetime import date                          # noqa: E402

import app as A                                    # noqa: E402
import plaid_client as pc                          # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
UID = 1


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


class Fake:
    """Scripted Plaid. account_id values differ per connection, as they really do."""
    env = 'sandbox'

    def __init__(self):
        self.item_id = 'plaid-item-A'
        self.token = 'access-A'
        self.institution_id = 'ins_sofi'
        self.accounts = []
        self.removed = []
        self.txns = []

    def available(self):
        return True

    def exchange_public_token(self, public_token):
        return {'access_token': self.token, 'item_id': self.item_id}

    def item_get(self, t):
        return {'item': {'institution_id': self.institution_id}}

    def institution_get(self, i):
        return {'institution': {'name': 'SoFi', 'institution_id': i,
                                'products': ['transactions', 'liabilities']}}

    def accounts_get(self, t):
        return {'accounts': self.accounts}

    def transactions_sync(self, t, cursor=None, count=500):
        return {'added': list(self.txns), 'modified': [], 'removed': [],
                'next_cursor': 'c', 'has_more': False}

    def item_remove(self, t):
        self.removed.append(t)
        return {'removed': True}

    def liabilities_get(self, t, account_ids=None):
        return {'liabilities': {}}

    def investments_holdings_get(self, t, account_ids=None):
        return {'holdings': [], 'securities': []}


FAKE = Fake()
A._plaid = lambda: FAKE


def acct(aid, name, mask, subtype='checking', typ='depository', bal=100.0):
    return {'account_id': aid, 'name': name, 'mask': mask, 'type': typ,
            'subtype': subtype, 'balances': {'current': bal, 'iso_currency_code': 'USD'}}


def client_for(uid):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    return c


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.FinanceAccount(id=1, user_id=UID, name='Checking', type='checking',
                                    balance=0.0))
    db.session.add(A.FinanceAccount(id=2, user_id=UID, name='Savings', type='savings',
                                    balance=0.0))
    db.session.commit()

admin = client_for(UID)

print('\n--- the first connection goes in as normal ---')
FAKE.accounts = [acct('A-chk', 'SoFi Checking', '0852'),
                 acct('A-sav', 'SoFi Savings', '3808', subtype='savings', bal=500.0)]
r = admin.post('/api/plaid/exchange', json={'public_token': 'public-1'})
check('created', r.status_code == 201, (r.status_code, r.get_json()))
with app.app_context():
    first = A.PlaidItem.query.filter_by(user_id=UID).one()
    first_id = first.id
    # Link the accounts to records and give it some history, as a real one would have.
    A._sync_plaid_accounts(first)
    db.session.commit()
    for a in A.PlaidAccount.query.filter_by(item_id=first_id).all():
        a.linked_account_id = 1 if a.mask == '0852' else 2
    db.session.add_all([
        A.SpendTransaction(user_id=UID, source='plaid', external_id='plaid:old-1',
                           plaid_account_id='A-chk', description='COFFEE', amount=4.5,
                           posted_at=date(2026, 10, 1), category='food'),
        A.SpendTransaction(user_id=UID, source='plaid', external_id='plaid:old-2',
                           plaid_account_id='A-sav', description='MUDFLAP', amount=174.7,
                           posted_at=date(2026, 10, 9), category='transportation'),
    ])
    db.session.add(A.PlaidDeposit(user_id=UID, external_id='dep:old-1',
                                  plaid_account_id='A-chk', description='PAY',
                                  amount=1000.0, posted_at=date(2026, 10, 2)))
    db.session.commit()

print('\n--- A SECOND CONNECTION TO A WORKING BANK IS REFUSED ---')
FAKE.item_id, FAKE.token = 'plaid-item-B', 'access-B'
r = admin.post('/api/plaid/exchange', json={'public_token': 'public-2'})
body = r.get_json()
check('409, not a silent second connection', r.status_code == 409, (r.status_code, body))
check('with a code a caller can branch on',
      body.get('code') == 'ALREADY_CONNECTED', body)
check('it names the existing connection so the UI can offer update mode',
      body.get('item_id') == first_id, body)
check('and says what to do instead', 'update' in (body.get('hint') or '').lower(), body)
check('the message explains the cost, not just the refusal',
      'duplicates your history' in (body.get('error') or ''), body.get('error'))
with app.app_context():
    check('NO second connection was created',
          A.PlaidItem.query.filter_by(user_id=UID).count() == 1,
          A.PlaidItem.query.filter_by(user_id=UID).count())
    check('and no history was re-imported',
          A.SpendTransaction.query.filter_by(user_id=UID).count() == 2)

print('\n--- but a genuine second login at the same bank is still possible ---')
r = admin.post('/api/plaid/exchange', json={'public_token': 'public-2',
                                            'allow_duplicate': True})
check('the override is honoured', r.status_code == 201, (r.status_code, r.get_json()))
check('and it does NOT adopt -- two logins were asked for, not a replacement',
      'adopted' not in (r.get_json() or {}), r.get_json())
with app.app_context():
    check('there are now two', A.PlaidItem.query.filter_by(user_id=UID).count() == 2)
    second = A.PlaidItem.query.filter_by(user_id=UID, item_id='plaid-item-B').one()
    db.session.delete(second)         # put it back for the next section
    db.session.commit()
    check('cleaned up', A.PlaidItem.query.filter_by(user_id=UID).count() == 1)

print('\n--- A DEAD CONNECTION IS REPLACED, AND ITS RECORDS COME ACROSS ---')
with app.app_context():
    it = db.session.get(A.PlaidItem, first_id)
    A._record_item_error(it, pc.PlaidError('gone', code='ITEM_NOT_FOUND'))
    db.session.commit()
    check('it reports that only a new connection will do', it.recovery() == 'relink',
          it.recovery())

FAKE.item_id, FAKE.token = 'plaid-item-C', 'access-C'
FAKE.accounts = [acct('C-chk', 'SoFi Checking', '0852'),
                 acct('C-sav', 'SoFi Savings', '3808', subtype='savings', bal=500.0)]
r = admin.post('/api/plaid/exchange', json={'public_token': 'public-3'})
body = r.get_json()
check('allowed through, no override needed', r.status_code == 201, (r.status_code, body))
ad = body.get('adopted') or {}
check('it reports what it took over', ad.get('from_item') == first_id, ad)
check('both accounts matched on mask AND subtype', ad.get('accounts_matched') == 2, ad)
check('both links carried', ad.get('links_carried') == 2, ad)
check('and the history followed', ad.get('rows_remapped') == 2, ad)
check('deposits too', ad.get('deposits_remapped') == 1, ad)
check('nothing was ambiguous or unmatched',
      not ad.get('ambiguous') and not ad.get('unmatched'), ad)

with app.app_context():
    check('the dead connection is gone', db.session.get(A.PlaidItem, first_id) is None)
    check('and took its accounts with it',
          A.PlaidAccount.query.filter_by(item_id=first_id).count() == 0)
    new = A.PlaidItem.query.filter_by(user_id=UID).one()
    chk = A.PlaidAccount.query.filter_by(user_id=UID, account_id='C-chk').one()
    sav = A.PlaidAccount.query.filter_by(user_id=UID, account_id='C-sav').one()
    check('the checking account inherited its record', chk.linked_account_id == 1,
          chk.linked_account_id)
    check('and the savings account the right one, not the other',
          sav.linked_account_id == 2, sav.linked_account_id)
    check('THE HISTORY NOW POINTS AT THE NEW ACCOUNTS',
          A.SpendTransaction.query.filter_by(user_id=UID,
                                             plaid_account_id='C-chk').count() == 1,
          [t.plaid_account_id for t in A.SpendTransaction.query.filter_by(user_id=UID)])
    check('none of it still points at the old ones',
          A.SpendTransaction.query.filter(
              A.SpendTransaction.plaid_account_id.in_(['A-chk', 'A-sav'])).count() == 0)
    check('the categorisation on those rows survived',
          {t.category for t in A.SpendTransaction.query.filter_by(user_id=UID)}
          == {'food', 'transportation'},
          [(t.description, t.category) for t in A.SpendTransaction.query.filter_by(user_id=UID)])
    check('the deposit moved as well',
          A.PlaidDeposit.query.filter_by(user_id=UID,
                                         plaid_account_id='C-chk').count() == 1)
    check('and the balance is fed by exactly one account now',
          float(db.session.get(A.FinanceAccount, 2).balance) == 500.0,
          db.session.get(A.FinanceAccount, 2).balance)
    new_id = new.id

print('\n--- THE FIRST REPLAY OF AN ADOPTED CONNECTION DOES NOT RE-IMPORT ITS HISTORY ---')
# Plaid's transaction ids are per Item, so the replacement delivers the same three rows
# under ids the ledger has never seen; external_id dedupe recognises none of them. In
# production that was 47 spend rows and 31 deposits, $99,516 of phantom activity. The
# gate is a DATE watermark per account, deliberately not an amount match: a row dated
# after everything held must still arrive, and so must a different amount on the
# boundary day. Only a same-day exact amount is taken as already held.


def txn(tid, acct, name, amount, day, income=False):
    t = {'transaction_id': tid, 'account_id': acct, 'name': name, 'merchant_name': name,
         'amount': amount, 'date': day, 'pending': False}
    if income:
        t['personal_finance_category'] = {'primary': 'INCOME', 'detailed': 'INCOME_WAGES'}
    return t


FAKE.txns = [
    txn('new-1', 'C-chk', 'COFFEE', 4.5, '2026-10-01'),                  # held: before the watermark
    txn('new-2', 'C-chk', 'PAY', -1000.0, '2026-10-02', income=True),    # held: ON it, same amount
    txn('new-3', 'C-sav', 'MUDFLAP', 174.7, '2026-10-09'),               # held: on it
    txn('new-4', 'C-chk', 'NETFLIX', 26.99, '2026-10-20'),               # NEW: after the watermark
    txn('new-5', 'C-sav', 'DTE', 52.10, '2026-10-09'),                   # NEW: boundary day, other amount
]
with app.app_context():
    it = db.session.get(A.PlaidItem, new_id)
    check('the replacement is marked as having adopted', it.adopted_at is not None)
    check('and says so to the UI', bool(it.to_dict().get('adopted_at')), it.to_dict())
r = admin.post('/api/plaid/items/%d/sync' % new_id)
body = r.get_json() or {}
check('200', r.status_code == 200, (r.status_code, body))
check('ONLY THE TWO GENUINELY NEW ROWS ARE ADDED', body.get('added') == 2, body)
check('the three already held are reported as such, not silently dropped',
      body.get('already_held') == 3, body)
with app.app_context():
    rows = A.SpendTransaction.query.filter_by(user_id=UID).order_by(A.SpendTransaction.id).all()
    check('four spend rows, not seven', len(rows) == 4,
          [(t.description, float(t.amount)) for t in rows])
    check('THE PAYCHECK WAS NOT RECORDED A SECOND TIME',
          A.PlaidDeposit.query.filter_by(user_id=UID).count() == 1,
          A.PlaidDeposit.query.filter_by(user_id=UID).count())
    check('the row dated after the watermark landed', any(t.description == 'NETFLIX' for t in rows))
    check('the boundary-day row with a different amount landed too',
          any(t.description == 'DTE' for t in rows))
    check('and the hand-categorisation on the held rows is untouched',
          {t.category for t in rows if t.description in ('COFFEE', 'MUDFLAP')}
          == {'food', 'transportation'}, [(t.description, t.category) for t in rows])
r = admin.get('/api/plaid/duplicates')
check('so the duplicate report has nothing to say', r.get_json().get('count') == 0, r.get_json())

print('\n--- a backfill of an adopted connection is gated the same way ---')
with app.app_context():
    out = A._plaid_sync_item(db.session.get(A.PlaidItem, new_id), backfill=True)
    check('nothing added', out.get('added') == 0, out)
    check('all five count as held -- the two it added now sit on the watermark day',
          out.get('already_held') == 5, out)
    check('still four rows', A.SpendTransaction.query.filter_by(user_id=UID).count() == 4)

print('\n--- an ordinary incremental sync is NOT gated: the cursor has moved on ---')
FAKE.txns = [txn('new-6', 'C-chk', 'GRANGER', 31.0, '2026-10-25')]
r = admin.post('/api/plaid/items/%d/sync' % new_id)
body = r.get_json() or {}
check('the new row is added', body.get('added') == 1, body)
check('and nothing is reported as held, because nothing old was delivered',
      'already_held' not in body, body)
FAKE.txns = []

print('\n--- a mask it cannot place is reported, never guessed ---')
with app.app_context():
    it = db.session.get(A.PlaidItem, new_id)
    A._record_item_error(it, pc.PlaidError('gone', code='ITEM_NOT_FOUND'))
    db.session.commit()
FAKE.item_id, FAKE.token = 'plaid-item-D', 'access-D'
# 0852 arrives as a SAVINGS account this time, and a mask that was never seen before.
FAKE.accounts = [acct('D-sav2', 'SoFi Savings', '0852', subtype='savings'),
                 acct('D-new', 'SoFi Vault', '9999', subtype='savings')]
r = admin.post('/api/plaid/exchange', json={'public_token': 'public-4'})
ad = r.get_json().get('adopted') or {}
check('the subtype mismatch is NOT matched to the old checking account',
      ad.get('accounts_matched') == 0, ad)
check('both are reported as unmatched instead',
      len(ad.get('unmatched') or []) == 2, ad)
check('so no link was invented', ad.get('links_carried') == 0, ad)
with app.app_context():
    check('and no history was moved onto the wrong account',
          ad.get('rows_remapped') == 0, ad)

print('\n--- the duplicate detector: reports, and changes nothing ---')
with app.app_context():
    newest = A.PlaidItem.query.filter_by(user_id=UID).one()
    a = A.PlaidAccount.query.filter_by(user_id=UID, account_id='D-sav2').one()
    db.session.add_all([
        # same amount, two days apart, description differs only in the separator
        A.SpendTransaction(user_id=UID, source='plaid', external_id='plaid:x1',
                           plaid_account_id='D-sav2', description='To Checking - 0852',
                           amount=750.0, posted_at=date(2026, 8, 16), category='transfer'),
        A.SpendTransaction(user_id=UID, source='plaid', external_id='plaid:x2',
                           plaid_account_id='D-sav2', description='To Checking • 0852',
                           amount=750.0, posted_at=date(2026, 8, 18), category=None),
        # same amount but far apart: two separate payments, not a duplicate
        A.SpendTransaction(user_id=UID, source='plaid', external_id='plaid:y1',
                           plaid_account_id='D-sav2', description='RENT',
                           amount=99.0, posted_at=date(2026, 8, 1), category='housing'),
        A.SpendTransaction(user_id=UID, source='plaid', external_id='plaid:y2',
                           plaid_account_id='D-sav2', description='RENT',
                           amount=99.0, posted_at=date(2026, 9, 1), category='housing'),
    ])
    db.session.commit()
    before = A.SpendTransaction.query.filter_by(user_id=UID).count()

r = admin.get('/api/plaid/duplicates')
body = r.get_json()
check('200', r.status_code == 200, r.status_code)
check('the shifted pair is found despite a different date and description',
      body.get('count') == 1, body)
check('it reports the value involved', body.get('extra_value') == 750.0, body)
pair = (body.get('pairs') or [{}])[0]
check('the OLDER row is the keeper -- it carries the categorisation',
      pair.get('keep', {}).get('category') == 'transfer', pair)
check('and the LATER row is the one flagged, not the other way round',
      pair.get('duplicate', {}).get('posted_at') == '2026-08-18'
      and pair.get('keep', {}).get('posted_at') == '2026-08-16', pair)
check('the pair is identified by id, so a human can go and look',
      pair.get('keep', {}).get('id') < pair.get('duplicate', {}).get('id'), pair)
check('two real payments a month apart are NOT called duplicates',
      all('RENT' not in str(p) for p in body.get('pairs') or []), body.get('pairs'))
with app.app_context():
    check('NOTHING WAS DELETED',
          A.SpendTransaction.query.filter_by(user_id=UID).count() == before, before)

r = admin.get('/api/plaid/duplicates?days=0')
check('a zero tolerance only matches same-day rows',
      r.get_json().get('count') == 0, r.get_json())
r = admin.get('/api/plaid/duplicates?days=40')
check('an absurd tolerance is clamped rather than honoured',
      r.get_json().get('tolerance_days') == 14, r.get_json())
with app.app_context():
    # Two genuinely separate charges of the same amount, ten days apart. Nothing
    # distinguishes them from a duplicate by amount and date alone.
    db.session.add_all([
        A.SpendTransaction(user_id=UID, source='plaid', external_id='plaid:z1',
                           plaid_account_id='D-sav2', description='MUGG & BOPPS',
                           amount=55.0, posted_at=date(2026, 7, 1), category='food'),
        A.SpendTransaction(user_id=UID, source='plaid', external_id='plaid:z2',
                           plaid_account_id='D-sav2', description='MUGG & BOPPS',
                           amount=55.0, posted_at=date(2026, 7, 11), category='food'),
    ])
    db.session.commit()
r = admin.get('/api/plaid/duplicates?days=4')
check('a tight window leaves those two alone', r.get_json().get('count') == 1,
      r.get_json())
r = admin.get('/api/plaid/duplicates?days=14')
check('A WIDER ONE CALLS THEM DUPLICATES, WHICH THEY ARE NOT -- precisely why this '
      'reports and never deletes', r.get_json().get('count') == 2, r.get_json())
r = admin.get('/api/plaid/duplicates?days=lots')
check('a non-number is refused', r.status_code == 400, r.status_code)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PLAID RELINK CHECKS PASSED')
