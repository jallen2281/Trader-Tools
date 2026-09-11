"""A bill can be charged to a credit card, not just drawn from a bank account.

Property tax on a rewards card, a tuition instalment, an annual premium -- these are paid
by card routinely, and a bill that could only point at a FinanceAccount had to claim it
came out of checking. That is the wrong source and, more importantly, the wrong DATE: the
cash leaves when the card is paid, which can be weeks later. Putting a tax bill on a card
deliberately to buy that float is a real tactic, and the ledger could not express it.

The trap this guards is paid_by_debt_id vs linked_debt_id. They point opposite ways --
one is the card a bill is CHARGED to, the other is the debt a bill PAYS OFF -- and
confusing them would book a fresh charge as debt service.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='billcard_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'b.db').replace(os.sep, '/')
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
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.User(id=2, google_id='g2', email='other@x.com', name='Other', role='user',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.FinanceAccount(id=10, user_id=1, name='SoFi Checking', type='checking',
                                    balance=3157.20))
    db.session.add(A.Debt(id=20, user_id=1, name='Discover', type='credit_card',
                          balance=0, apr=26.49, min_payment=0))
    db.session.add(A.Debt(id=21, user_id=1, name='Amex', type='credit_card',
                          balance=33442.61, apr=24.49, min_payment=986))
    db.session.add(A.Debt(id=99, user_id=2, name='Someone else card', type='credit_card',
                          balance=500, apr=20, min_payment=25))
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

print('\n--- the case that prompted this: property tax onto a zero-balance card ---')
r = c.post('/api/finance/bills', json={'name': 'Property tax - summer', 'category': 'taxes',
                                       'amount': 2744.82, 'frequency': 'annual',
                                       'paid_from': 'debt:20'})
check('the bill saves', r.status_code == 201, r.get_json())
b = r.get_json()
bid = b['id']
check('it points at the card', b['paid_by_debt_id'] == 20, b)
check('and not at a bank account', b['from_account_id'] is None, b)
check('paid_from round-trips', b['paid_from'] == 'debt:20', b['paid_from'])

print('\n--- a card is not the debt the bill pays off ---')
check('charging it to a card leaves linked_debt_id alone',
      b['linked_debt_id'] is None, b['linked_debt_id'])

print('\n--- switching sources replaces, never accumulates ---')
r = c.put('/api/finance/bills/%d' % bid, json={'paid_from': 'account:10'})
b = r.get_json()
check('now the checking account', b['from_account_id'] == 10, b)
check('and the card is released', b['paid_by_debt_id'] is None, b)
check('paid_from follows', b['paid_from'] == 'account:10', b['paid_from'])
r = c.put('/api/finance/bills/%d' % bid, json={'paid_from': 'debt:20'})
check('and back again', r.get_json()['paid_by_debt_id'] == 20, r.get_json())

print('\n--- clearing it ---')
r = c.put('/api/finance/bills/%d' % bid, json={'paid_from': ''})
b = r.get_json()
check('both sides go', b['paid_by_debt_id'] is None and b['from_account_id'] is None, b)
check('paid_from is null, not a dangling prefix', b['paid_from'] is None, b['paid_from'])

print('\n--- a bill cannot be charged to the card it pays off ---')
r = c.post('/api/finance/bills', json={'name': 'Amex', 'category': 'debt', 'amount': 1062.62,
                                       'frequency': 'monthly', 'linked_debt_id': 21,
                                       'paid_from': 'debt:21'})
check('refused rather than half-applied', r.status_code == 400, (r.status_code, r.get_json()))
with app.app_context():
    check('and nothing was written',
          A.RecurringBill.query.filter_by(name='Amex').count() == 0)

print('\n--- paying the Amex bill FROM a different card is allowed, if odd ---')
r = c.post('/api/finance/bills', json={'name': 'Amex', 'category': 'debt', 'amount': 1062.62,
                                       'frequency': 'monthly', 'linked_debt_id': 21,
                                       'paid_from': 'debt:20'})
check('accepted', r.status_code == 201, r.get_json())
b = r.get_json()
check('pays off 21, charged to 20 -- the two fields stay distinct',
      (b['linked_debt_id'], b['paid_by_debt_id']) == (21, 20), b)

print("\n--- another user's card is not selectable ---")
r = c.post('/api/finance/bills', json={'name': 'Sneaky', 'category': 'other', 'amount': 10,
                                       'frequency': 'monthly', 'paid_from': 'debt:99'})
b = r.get_json()
check('the foreign card is dropped, not honoured', b['paid_by_debt_id'] is None, b)

print('\n--- junk does not crash or half-set ---')
for junk in ('debt:', 'debt:abc', 'account:9999', 'nonsense', 'debt:20:extra', ':', '5'):
    r = c.put('/api/finance/bills/%d' % bid, json={'paid_from': junk})
    ok = r.status_code == 200 and r.get_json()['paid_from'] is None
    check('%-16r -> cleared, 200' % junk, ok, (r.status_code, r.get_json().get('paid_from')))

print('\n--- an untouched bill keeps its source ---')
c.put('/api/finance/bills/%d' % bid, json={'paid_from': 'debt:20'})
r = c.put('/api/finance/bills/%d' % bid, json={'amount': 2800.00})
b = r.get_json()
check('editing the amount does not clear the card', b['paid_by_debt_id'] == 20, b)
check('the amount did change', b['amount'] == 2800.00, b['amount'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL BILL-PAID-BY-CARD CHECKS PASSED')
