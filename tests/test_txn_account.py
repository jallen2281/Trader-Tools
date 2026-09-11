"""Every transaction knows which account or card it came from.

Imported rows already carried the Plaid account they arrived on, and every PlaidAccount
already knew what the user had linked it to. Nothing joined the two, so the ledger showed a
blank "from" on 243 of 244 rows — and for the 165 on credit cards there was no field that
could have held the answer, because account_id is a foreign key to bank accounts and a card
is a Debt.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='txnacct_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 't.db').replace(os.sep, '/')
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


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add_all([
        A.FinanceAccount(id=5, user_id=1, name='Checking', type='checking', balance=1000),
        A.Debt(id=7, user_id=1, name='Prime Visa', type='credit_card', balance=400,
               apr=24.99),
        A.PlaidItem(id=1, user_id=1, item_id='it', access_token_enc=b'x',
                    institution_name='Chase'),
        A.PlaidAccount(id=30, user_id=1, item_id=1, account_id='acc-chk', name='Checking',
                       mask='1349', type='depository', subtype='checking'),
        A.PlaidAccount(id=31, user_id=1, item_id=1, account_id='acc-visa',
                       name='CREDIT CARD', mask='4831', type='credit',
                       subtype='credit card'),
    ])
    db.session.add_all([
        A.SpendTransaction(user_id=1, external_id='plaid:a', source='plaid',
                           plaid_account_id='acc-visa', posted_at=TODAY, amount=51.20,
                           description='STARBUCKS', category='food'),
        A.SpendTransaction(user_id=1, external_id='plaid:b', source='plaid',
                           plaid_account_id='acc-visa', posted_at=TODAY, amount=88.00,
                           description='HOME DEPOT', category='other'),
        A.SpendTransaction(user_id=1, external_id='plaid:c', source='plaid',
                           plaid_account_id='acc-chk', posted_at=TODAY, amount=1800.00,
                           description='RENT', category='housing'),
    ])
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

print('\n--- before anything is linked, nothing can be attributed ---')
with app.app_context():
    check('every imported row starts with a blank from-account',
          A.SpendTransaction.query.filter(A.SpendTransaction.account_id.is_(None),
                                          A.SpendTransaction.debt_id.is_(None)).count() == 3)

print('\n--- linking a card attributes its transactions to the card ---')
r = c.put('/api/plaid/accounts/31/link', json={'kind': 'debt', 'id': 7})
check('the link reports how many moved', r.get_json().get('transactions_attributed') == 2,
      r.get_json())
with app.app_context():
    visa = A.SpendTransaction.query.filter_by(plaid_account_id='acc-visa').all()
    check('card purchases point at the Debt', all(t.debt_id == 7 for t in visa), visa)
    check('and NOT at a bank account', all(t.account_id is None for t in visa))
    check('the checking row is untouched by that link',
          A.SpendTransaction.query.filter_by(plaid_account_id='acc-chk').first().debt_id is None)

print('\n--- and linking a bank account does the same on its side ---')
c.put('/api/plaid/accounts/30/link', json={'kind': 'account', 'id': 5})
with app.app_context():
    chk = A.SpendTransaction.query.filter_by(plaid_account_id='acc-chk').first()
    check('it points at the FinanceAccount', chk.account_id == 5, chk.account_id)
    check('and not at a debt', chk.debt_id is None)
    check('nothing is left unattributed',
          A.SpendTransaction.query.filter(A.SpendTransaction.account_id.is_(None),
                                          A.SpendTransaction.debt_id.is_(None)).count() == 0)

print('\n--- exactly one of the two is ever set ---')
with app.app_context():
    both = A.SpendTransaction.query.filter(A.SpendTransaction.account_id.isnot(None),
                                           A.SpendTransaction.debt_id.isnot(None)).count()
    check('never both at once', both == 0, both)

print('\n--- unlinking clears the attribution rather than leaving it stale ---')
c.put('/api/plaid/accounts/31/link', json={'kind': ''})
with app.app_context():
    check('the card rows no longer claim a debt that does not claim them',
          A.SpendTransaction.query.filter_by(plaid_account_id='acc-visa',
                                             debt_id=7).count() == 0)
c.put('/api/plaid/accounts/31/link', json={'kind': 'debt', 'id': 7})

print('\n--- re-running is idempotent ---')
r = c.post('/api/plaid/accounts/attribute')
check('a second pass moves nothing', r.get_json()['attributed'] == 0, r.get_json())
check('and reports none left over', r.get_json()['still_unattributed'] == 0, r.get_json())

print('\n--- a manual transaction can name a card ---')
r = c.post('/api/finance/transactions', json={'description': 'Fuel', 'amount': 62.10,
                                              'category': 'transportation',
                                              'paid_from': 'debt:7'})
check('created against the card', r.status_code == 201 and r.get_json()['debt_id'] == 7,
      r.get_json())
check('paid_from round-trips in the same form the form uses',
      r.get_json()['paid_from'] == 'debt:7', r.get_json())
tid = r.get_json()['id']
r = c.put('/api/finance/transactions/%d' % tid, json={'paid_from': 'account:5'})
check('switching to a bank account clears the card',
      r.get_json()['account_id'] == 5 and r.get_json()['debt_id'] is None, r.get_json())
r = c.put('/api/finance/transactions/%d' % tid, json={'paid_from': ''})
check('and it can be cleared entirely',
      r.get_json()['account_id'] is None and r.get_json()['debt_id'] is None, r.get_json())

print('\n--- a card or account belonging to someone else is refused ---')
with app.app_context():
    db.session.add(A.User(id=2, google_id='g2', email='o@x.com', name='O', role='user',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.Debt(id=99, user_id=2, name='Not mine', type='credit_card', balance=1))
    db.session.commit()
r = c.put('/api/finance/transactions/%d' % tid, json={'paid_from': 'debt:99'})
check("another user's card is not accepted", r.get_json()['debt_id'] is None, r.get_json())
r = c.put('/api/finance/transactions/%d' % tid, json={'paid_from': 'debt:abc'})
check('and nonsense is ignored rather than crashing', r.status_code == 200)

print('\n--- a fresh sync attributes as it imports ---')
with app.app_context():
    db.session.add(A.SpendTransaction(user_id=1, external_id='plaid:d', source='plaid',
                                      plaid_account_id='acc-visa', posted_at=TODAY,
                                      amount=12.00, description='LATE ARRIVAL',
                                      category='food'))
    db.session.commit()
    moved = A._attribute_linked_transactions(1)
    db.session.commit()
    check('the new row is picked up', moved == 1, moved)
    check('and points at the card',
          A.SpendTransaction.query.filter_by(external_id='plaid:d').first().debt_id == 7)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL TRANSACTION ATTRIBUTION CHECKS PASSED')
