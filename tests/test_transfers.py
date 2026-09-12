"""A transfer moves money; it does not spend it.

Without a way to say "this went into that account", every movement looked like a purchase.
Real damage: savings -> checking -> card payment counted the same dollars three times, and
one month read as $75,706 of spending against $13,000 of income. Card payments are the
subtle half -- paying the Amex is not spending, because the purchases were already recorded
when the card was used.

So 'transfer' is a category, it carries a destination, and it is excluded from every
spend total while staying visible in the listing (a statement you cannot reconcile is
worse than one with transfers in it).
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='xfer_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 't.db').replace(os.sep, '/')
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


TODAY = None
with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.FinanceAccount(id=10, user_id=1, name='SoFi Checking', type='checking'))
    db.session.add(A.FinanceAccount(id=11, user_id=1, name='SoFi Savings', type='savings'))
    db.session.add(A.Debt(id=20, user_id=1, name='Amex', type='credit_card',
                          balance=33442.61, apr=24.49, min_payment=986))
    db.session.commit()
    TODAY = A.date.today().isoformat()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

print('\n--- transfer is a real category ---')
check("'transfer' is accepted", 'transfer' in A.BUDGET_CATEGORIES)
check('and is named as non-spend', 'transfer' in A.NON_SPEND_CATEGORIES)


def mk(**kw):
    body = {'posted_at': TODAY, 'description': 'x', 'amount': 100, 'category': 'other'}
    body.update(kw)
    return c.post('/api/finance/transactions', json=body)


print('\n--- savings to checking ---')
r = mk(description='To Checking - 0852', amount=7500, category='transfer',
       paid_from='account:11', transfer_to='account:10')
check('saves', r.status_code == 201, r.get_json())
t = r.get_json()
check('source recorded', t['paid_from'] == 'account:11', t['paid_from'])
check('destination recorded', t['transfer_to'] == 'account:10', t['transfer_to'])

print('\n--- a destination makes it a transfer, whatever the category said ---')
r = mk(description='moved some money', amount=2300, category='food',
       paid_from='account:11', transfer_to='account:10')
t = r.get_json()
check('category is corrected to transfer', t['category'] == 'transfer', t['category'])

print('\n--- paying a card is a transfer into the card ---')
r = mk(description='AMEX EPAYMENT', amount=7178, category='transfer',
       paid_from='account:10', transfer_to='debt:20')
t = r.get_json()
check('lands on the debt', t['to_debt_id'] == 20, t)
check('and not on an account', t['to_account_id'] is None, t)

print('\n--- none of it counts as spending ---')
with app.app_context():
    start, end = A._month_bounds(None)
    act = A._spend_actuals(1, start, end)
check('no transfer category in the spend rollup', 'transfer' not in act, act)
check('and it did not leak into another category',
      sum(act.values()) == 0, act)

print('\n--- but the rows are still listed and totalled separately ---')
r = c.get('/api/finance/transactions')
j = r.get_json()
check('all three are listed', j['count'] == 3, j['count'])
check('spend total is zero', j['total'] == 0.0, j['total'])
check('moved money is reported on its own',
      j['transfer_total'] == 7500 + 2300 + 7178, j['transfer_total'])
check('and counted', j['transfer_count'] == 3, j['transfer_count'])
check('by_category omits transfers',
      all(b['category'] != 'transfer' for b in j['by_category']), j['by_category'])

print('\n--- a real purchase is unaffected ---')
r = mk(description='Wegmans', amount=265.79, category='food', paid_from='account:10')
t = r.get_json()
check('stays food', t['category'] == 'food', t['category'])
check('has no destination', t['transfer_to'] is None, t['transfer_to'])
j = c.get('/api/finance/transactions').get_json()
check('and now the spend total is just the groceries', j['total'] == 265.79, j['total'])

print('\n--- a transfer into the account it came from is refused ---')
r = mk(description='nowhere', amount=50, category='transfer',
       paid_from='account:10', transfer_to='account:10')
check('400, not a silent no-op', r.status_code == 400, (r.status_code, r.get_json()))
r = mk(description='nowhere', amount=50, category='transfer',
       paid_from='debt:20', transfer_to='debt:20')
check('same for a card', r.status_code == 400, (r.status_code, r.get_json()))

print('\n--- the importer recognises movement on sight ---')
for desc, want in (('AMEX EPAYMENT', 'transfer'),
                   ('CITI CARD ONLINE', 'transfer'),
                   ('To Savings - 3808', 'transfer'),
                   ('SoFi Bank TRANSFER JAllen WEB', 'transfer'),
                   ('DTE ENERGY', 'utilities'),
                   ('Wegmans', 'food')):
    got = A._guess_spend_category(desc)
    check('%-32r -> %s' % (desc, want), got == want, got)

print('\n--- clearing a destination ---')
r = mk(description='undo me', amount=10, category='transfer',
       paid_from='account:11', transfer_to='account:10')
tid = r.get_json()['id']
r = c.put('/api/finance/transactions/%d' % tid, json={'transfer_to': ''})
t = r.get_json()
check('destination goes', t['transfer_to'] is None, t)
check('but the category stays transfer -- it was set deliberately',
      t['category'] == 'transfer', t['category'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL TRANSFER CHECKS PASSED')
