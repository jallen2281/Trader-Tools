"""A debt can carry fees that are not interest.

A tuition payment plan is the case: 0% APR, an enrolment fee each semester, and a
processing charge on every instalment. With only an APR field such a debt looks free, when
it can easily cost more to carry than a low-rate loan of the same size. Several unrelated
charges means several rows — one "fees" box could not hold them with their names intact.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='debtfee_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'd.db').replace(os.sep, '/')
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
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

# The ASU shape: no interest, a per-semester plan fee, a charge on every instalment, and a
# one-off set-up charge.
FEES = [
    {'label': 'Payment plan enrolment', 'amount': 35.00, 'frequency': 'semester'},
    {'label': 'Processing fee', 'amount': 2.50, 'frequency': 'monthly'},
    {'label': 'Account set-up', 'amount': 50.00, 'frequency': 'one_time'},
]

print('\n--- several fees, each with its own name and cadence ---')
r = c.post('/api/finance/debts', json={'name': 'ASU tuition plan', 'type': 'other',
                                       'balance': 4000, 'apr': 0, 'min_payment': 515,
                                       'fee_lines': FEES})
check('the debt saves', r.status_code == 201, r.get_json())
d = r.get_json()
check('all three rows survive', len(d['fee_lines']) == 3, d['fee_lines'])
check('recurring fees annualise by cadence',
      d['annual_fees'] == round(35 * 2 + 2.50 * 12, 2), d['annual_fees'])
check('a one-off is NOT annualised', d['one_time_fees'] == 50.00, d['one_time_fees'])
check('it is excluded from the yearly figure -- it is a cost of taking the debt on, '
      'not of carrying it', d['annual_fees'] == 100.00, d['annual_fees'])

print('\n--- fees become a rate, so a 0% plan is comparable to a real loan ---')
check('the stated APR is still zero', d['apr'] == 0.0, d['apr'])
check('but the effective rate is not', d['effective_apr'] == 2.5, d['effective_apr'])
check('monthly cost is interest plus fees',
      d['monthly_cost'] == round(100.00 / 12, 2), d['monthly_cost'])

print('\n--- the rate rises as the balance falls, which is the point ---')
did = d['id']
for bal, expect in ((4000, 2.5), (2000, 5.0), (1000, 10.0), (500, 20.0)):
    r = c.put('/api/finance/debts/%d' % did, json={'balance': bal})
    check('$%-5d balance -> %.1f%% effective' % (bal, expect),
          r.get_json()['effective_apr'] == expect, r.get_json()['effective_apr'])
c.put('/api/finance/debts/%d' % did, json={'balance': 4000})

print('\n--- a debt with no fees is unaffected ---')
r = c.post('/api/finance/debts', json={'name': 'Car', 'type': 'auto', 'balance': 26000,
                                       'apr': 8.1, 'min_payment': 650})
d2 = r.get_json()
check('no fee rows', d2['fee_lines'] == [], d2['fee_lines'])
check('annual fees zero', d2['annual_fees'] == 0.0)
check('effective rate equals the APR', d2['effective_apr'] == 8.1, d2['effective_apr'])
check('monthly cost is just the interest',
      d2['monthly_cost'] == d2['monthly_interest'], (d2['monthly_cost'], d2['monthly_interest']))

print('\n--- rows can be added and removed ---')
r = c.put('/api/finance/debts/%d' % did, json={'fee_lines': FEES[:1]})
check('removing rows sticks', len(r.get_json()['fee_lines']) == 1, r.get_json()['fee_lines'])
check('and the yearly total follows', r.get_json()['annual_fees'] == 70.00,
      r.get_json()['annual_fees'])
r = c.put('/api/finance/debts/%d' % did, json={'fee_lines': []})
check('clearing them all is allowed', r.get_json()['fee_lines'] == [], r.get_json())
check('and the debt reverts to its stated rate',
      r.get_json()['effective_apr'] == 0.0, r.get_json()['effective_apr'])
c.put('/api/finance/debts/%d' % did, json={'fee_lines': FEES})

print('\n--- nonsense rows are dropped, not stored ---')
r = c.put('/api/finance/debts/%d' % did, json={'fee_lines': [
    {'label': 'Real', 'amount': 25, 'frequency': 'annual'},
    {'label': 'Zero', 'amount': 0, 'frequency': 'annual'},
    {'label': 'Junk', 'amount': 'free', 'frequency': 'annual'},
    {'label': 'Bad cadence', 'amount': 10, 'frequency': 'whenever'},
]})
kept = r.get_json()['fee_lines']
check('zero and non-numeric rows go', len(kept) == 2, kept)
check('an unknown cadence falls back to one-off, which never annualises',
      [k for k in kept if k['label'] == 'Bad cadence'][0]['frequency'] == 'one_time', kept)
check('so a bad row cannot inflate the yearly figure',
      r.get_json()['annual_fees'] == 25.00, r.get_json()['annual_fees'])

print('\n--- a zero balance does not divide by zero ---')
with app.app_context():
    z = A.Debt(user_id=1, name='Paid off', balance=0, apr=0,
               fee_lines=[{'label': 'Annual fee', 'amount': 99, 'frequency': 'annual'}])
    check('effective rate falls back to the stated APR', z.effective_apr() == 0.0,
          z.effective_apr())
    check('but the fee is still reported', z.annual_fees() == 99.0, z.annual_fees())

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL DEBT FEE CHECKS PASSED')
