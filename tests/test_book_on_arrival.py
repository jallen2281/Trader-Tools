"""A synced transaction arrives in the book its account already names.

Written from what the household was doing by hand. Every card and bank account was linked
to a debt or account record, and every one of those records had a book. The sync read
none of it: each new row arrived with no book, was shown as "Personal (default)", and was
counted in no book's figures until somebody filed it. All 18 rows synced in the week to
2026-11-17 were then filed by hand into the very book their card already named.

And a pending charge that had been moved to the farm came back unfiled once it posted.
Plaid gives the posted transaction a NEW id and retires the pending one, so the filing
was undone without a trace.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='arrival_book_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'b.db').replace(os.sep, '/')
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
    """Scripted Plaid: each sync call returns the next page in `pages`."""
    env = 'sandbox'

    def __init__(self):
        self.accounts = []
        self.pages = []

    def accounts_get(self, t):
        return {'accounts': self.accounts}

    def transactions_sync(self, t, cursor=None, count=500):
        page = self.pages.pop(0) if self.pages else {}
        return {'added': page.get('added', []), 'modified': page.get('modified', []),
                'removed': page.get('removed', []), 'next_cursor': 'c', 'has_more': False}

    def liabilities_get(self, t, account_ids=None):
        return {'liabilities': {}}

    def investments_holdings_get(self, t, account_ids=None):
        return {'holdings': [], 'securities': []}


FAKE = Fake()
A._plaid = lambda: FAKE


def acct(aid, name, mask, typ='credit', subtype='credit card'):
    return {'account_id': aid, 'name': name, 'mask': mask, 'type': typ, 'subtype': subtype,
            'balances': {'current': 0.0, 'iso_currency_code': 'USD'}}


def txn(tid, account, amount, name, day, pending=False, pending_id=None):
    t = {'transaction_id': tid, 'account_id': account, 'amount': amount, 'name': name,
         'merchant_name': None, 'date': day, 'pending': pending,
         'personal_finance_category': {'primary': 'GENERAL_MERCHANDISE'}}
    if pending_id:
        t['pending_transaction_id'] = pending_id
    return t


def row(tid):
    return A.SpendTransaction.query.filter_by(user_id=UID, external_id='plaid:' + tid).first()


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
    farm = A.Entity(id=1, user_id=UID, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    home = A.Entity(id=2, user_id=UID, name='Personal finance', kind='personal')
    db.session.add_all([farm, home])
    db.session.add(A.Debt(id=1, user_id=UID, name='Amex', type='credit_card', entity_id=2))
    db.session.add(A.Debt(id=2, user_id=UID, name='Menards Card', type='credit_card'))  # no book
    db.session.add(A.FinanceAccount(id=1, user_id=UID, name='Farm checking', type='checking',
                                    balance=0.0, entity_id=1))
    item = A.PlaidItem(user_id=UID, item_id='item-1', institution_name='Bank',
                       access_token_enc=pc.encrypt_token('access-1'), status='active')
    db.session.add(item)
    db.session.commit()
    ITEM = item.id
    FAKE.accounts = [acct('amex', 'Amex EveryDay', '2001'),
                     acct('menards', 'Menards BIG Card', '4066'),
                     acct('chk', 'Farm Checking', '1111', typ='depository', subtype='checking'),
                     acct('loose', 'Some Card', '9999')]
    A._sync_plaid_accounts(item)
    db.session.commit()
    links = {'amex': ('debt', 1), 'menards': ('debt', 2), 'chk': ('account', 1)}
    for pa in A.PlaidAccount.query.filter_by(user_id=UID).all():
        kind, rid = links.get(pa.account_id, (None, None))
        if kind == 'debt':
            pa.linked_debt_id = rid
        elif kind == 'account':
            pa.linked_account_id = rid
    db.session.commit()


def sync():
    with app.app_context():
        out = A._plaid_sync_item(db.session.get(A.PlaidItem, ITEM))
        db.session.commit()
        return out


print('\n--- A NEW ROW TAKES THE BOOK OF THE ACCOUNT IT CAME FROM ---')
FAKE.pages = [{'added': [
    txn('t-amex', 'amex', 52.10, 'TARGET', '2026-11-10'),
    txn('t-chk', 'chk', 89.97, 'TRACTOR SUPPLY', '2026-11-10'),
    txn('t-menards', 'menards', 14.99, 'MENARDS', '2026-11-10'),
    txn('t-loose', 'loose', 5.00, 'SOMETHING', '2026-11-10'),
    txn('p-diesel', 'amex', 174.70, 'MUDFLAP', '2026-11-11', pending=True),
    txn('p-plain', 'amex', 31.00, 'SPEEDWAY', '2026-11-11', pending=True),
]}]
sync()
with app.app_context():
    check('a charge on the Amex is in the Amex\'s book (Personal)',
          row('t-amex').entity_id == 2, row('t-amex').entity_id)
    check('a charge from farm checking is in the farm book -- a linked ACCOUNT works too',
          row('t-chk').entity_id == 1, row('t-chk').entity_id)
    check('a card whose record has no book stays unfiled rather than guessed',
          row('t-menards').entity_id is None, row('t-menards').entity_id)
    check('an account linked to nothing stays unfiled',
          row('t-loose').entity_id is None, row('t-loose').entity_id)
    check('the pending charges arrive in their card\'s book as well',
          row('p-diesel').entity_id == 2 and row('p-plain').entity_id == 2,
          (row('p-diesel').entity_id, row('p-plain').entity_id))
    r = A._entity_report(UID, 2, 2026)
    check('and the Personal book counts the Amex row without anyone filing it',
          r['transactions'] == 3, r['transactions'])

print('\n--- THE POSTED COPY OF A PENDING CHARGE KEEPS THE BOOK IT WAS MOVED TO ---')
with app.app_context():
    row('p-diesel').entity_id = 1        # the user moves the tractor diesel to the farm
    row('t-amex').entity_id = 1          # and decides the Target run was farm supplies
    db.session.commit()
FAKE.pages = [{
    'added': [txn('x-diesel', 'amex', 174.70, 'MUDFLAP', '2026-11-12', pending_id='p-diesel'),
              txn('x-plain', 'amex', 31.00, 'SPEEDWAY', '2026-11-12', pending_id='p-plain')],
    'modified': [txn('t-amex', 'amex', 52.10, 'TARGET', '2026-11-10'),
                 txn('t-menards', 'menards', 14.99, 'MENARDS', '2026-11-10')],
    'removed': [{'transaction_id': 'p-diesel'}, {'transaction_id': 'p-plain'}],
}]
sync()
with app.app_context():
    check('the posted diesel is in the farm book, where the pending one was moved',
          row('x-diesel') is not None and row('x-diesel').entity_id == 1,
          row('x-diesel') and row('x-diesel').entity_id)
    check('the pending rows themselves are gone, so it is counted once',
          row('p-diesel') is None and row('p-plain') is None)
    check('a posted charge whose pending row was never moved takes the card\'s book',
          row('x-plain') is not None and row('x-plain').entity_id == 2,
          row('x-plain') and row('x-plain').entity_id)
    check('a `modified` does not put a row the user re-filed back in the card\'s book',
          row('t-amex').entity_id == 1, row('t-amex').entity_id)

print('\n--- THE BOOK IS SHOWN AND SET BESIDE THE ACCOUNT ---')
admin = client_for(UID)
r = admin.get('/api/plaid/accounts')
body = r.get_json()
by = {a['account_id']: a for a in body.get('accounts', [])}
check('the accounts list includes the books to choose from',
      sorted(b['name'] for b in body.get('books', [])) == ['Chicken Tales LLC', 'Personal finance'],
      body.get('books'))
check('the Amex shows Personal, and that it lives on the Amex debt',
      by['amex'].get('book_id') == 2
      and by['amex'].get('book_record') == {'kind': 'debt', 'id': 1, 'name': 'Amex'},
      (by['amex'].get('book_id'), by['amex'].get('book_record')))
check('farm checking shows the farm, on the account record',
      by['chk'].get('book_id') == 1 and (by['chk'].get('book_record') or {}).get('kind') == 'account',
      (by['chk'].get('book_id'), by['chk'].get('book_record')))
check('the Menards card shows no book but can be given one',
      by['menards'].get('book_id') is None and by['menards'].get('book_record', {}).get('id') == 2,
      (by['menards'].get('book_id'), by['menards'].get('book_record')))
check('an unlinked account has nowhere to keep a book, and says so by having no record',
      by['loose'].get('book_record') is None, by['loose'].get('book_record'))

r = admin.put('/api/finance/entity/debt/2', json={'entity_id': 1})
check('setting the Menards card\'s book through the record endpoint works', r.status_code == 200,
      (r.status_code, r.get_json()))
FAKE.pages = [{'added': [txn('t-menards-2', 'menards', 42.00, 'MENARDS', '2026-11-13')]}]
sync()
with app.app_context():
    check('and the next Menards charge arrives in the farm book',
          row('t-menards-2').entity_id == 1, row('t-menards-2').entity_id)
    check('while the Menards row already held keeps the book it had -- new rows only',
          row('t-menards').entity_id is None, row('t-menards').entity_id)

print('\n%d check(s) failed' % len(fails) if fails else '\nall checks passed')
sys.exit(1 if fails else 0)
