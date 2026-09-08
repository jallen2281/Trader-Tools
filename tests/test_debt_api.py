"""Debt payoff planning and the bill-to-debt link, wired into the application.

The link is the important half. RecurringBill.linked_debt_id had existed since the budgeting
module shipped and nothing read it, so a car payment recorded both as a Debt (for the
minimum) and as a bill (so it appears on the cash-flow calendar) was counted twice in
outflow — which halved the reported runway. There was no way to have both a correct runway
and a complete calendar.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='debtapi_')
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


def client_for(uid):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    return c


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add_all([
        A.FinanceAccount(user_id=1, name='Checking', type='checking', balance=6000),
        A.Debt(id=5, user_id=1, name='Car loan', type='auto', balance=18000, apr=7.2,
               min_payment=400),
        A.Debt(id=6, user_id=1, name='Visa', type='credit_card', balance=6000, apr=24.99,
               min_payment=180),
    ])
    db.session.commit()

me = client_for(1)


def picture():
    with app.app_context():
        return A._finance_full_picture(1)


print('\n--- with no bills, every debt payment counts once ---')
p = picture()
check('all debt service is unbilled', p['unbilled_debt_service'] == 580.0,
      p['unbilled_debt_service'])
check('none of it is inside the bills figure', p['billed_debt_service'] == 0.0,
      p['billed_debt_service'])
check('outflow is the debt service', p['monthly_outflow'] == 580.0, p['monthly_outflow'])
check('both debts are flagged as missing from the calendar',
      sorted(d['name'] for d in p['debts_without_bill']) == ['Car loan', 'Visa'],
      p['debts_without_bill'])

print('\n--- an UNLINKED bill for the same debt double-counts, as it always did ---')
r = me.post('/api/finance/bills', json={'name': 'Car payment', 'category': 'debt',
                                        'amount': 400, 'frequency': 'monthly', 'due_day': 5})
bill_id = r.get_json()['id']
p = picture()
check('the bill is counted', p['bills']['total_monthly'] == 400.0, p['bills']['total_monthly'])
check('and so is the debt minimum, because nothing connects them',
      p['monthly_outflow'] == 980.0, p['monthly_outflow'])

print('\n--- linking it is what makes the payment count once ---')
r = me.put('/api/finance/bills/%d' % bill_id, json={'linked_debt_id': 5})
check('the link round-trips', r.get_json()['linked_debt_id'] == 5, r.get_json())
p = picture()
check('outflow drops to the true figure', p['monthly_outflow'] == 580.0, p['monthly_outflow'])
check('the car payment is reported as already inside bills',
      p['billed_debt_service'] == 400.0, p['billed_debt_service'])
check('only the Visa is left unbilled', p['unbilled_debt_service'] == 180.0,
      p['unbilled_debt_service'])
check('and only the Visa is missing from the calendar',
      [d['name'] for d in p['debts_without_bill']] == ['Visa'], p['debts_without_bill'])
check('runway is measured against the deduplicated outflow',
      p['runway_months'] == round(6000 / 580.0, 1), p['runway_months'])

print('\n--- DTI is deliberately NOT deduplicated ---')
check('debt service still counts the scheduled minimum on every debt',
      p['outlook']['monthly_debt_service'] == 580.0,
      p['outlook']['monthly_debt_service'])

print('\n--- unlinking puts the double count back, so the link is doing the work ---')
me.put('/api/finance/bills/%d' % bill_id, json={'linked_debt_id': None})
check('outflow returns to 980', picture()['monthly_outflow'] == 980.0)
me.put('/api/finance/bills/%d' % bill_id, json={'linked_debt_id': 5})

print('\n--- an inactive bill no longer covers its debt ---')
me.put('/api/finance/bills/%d' % bill_id, json={'active': False})
p = picture()
check('the debt goes back to being unbilled', p['unbilled_debt_service'] == 580.0,
      p['unbilled_debt_service'])
me.put('/api/finance/bills/%d' % bill_id, json={'active': True})

print('\n--- the payoff plan ---')
d = me.get('/api/finance/debt-plan').get_json()
check('endpoint answers', d['debt_count'] == 2, d.get('debt_count'))
check('both strategies returned', 'avalanche' in d and 'snowball' in d, list(d))
check('a payoff date is produced', d['avalanche']['debt_free_on'], d['avalanche'])
check('what-if options are offered', len(d['what_if']) > 0, d['what_if'])
check('the monthly outlay is the sum of the minimums with no extra',
      d['avalanche']['monthly_outlay'] == 580.0, d['avalanche']['monthly_outlay'])

print('\n--- extra money changes the answer, and sticks ---')
r = me.put('/api/finance/debt-plan/extra', json={'extra_monthly': 300})
check('saving the extra succeeds', r.status_code == 200, r.get_json())
d2 = me.get('/api/finance/debt-plan').get_json()
check('it is remembered without being passed again', d2['extra_monthly'] == 300.0,
      d2['extra_monthly'])
check('the plan pays 300 more a month', d2['avalanche']['monthly_outlay'] == 880.0,
      d2['avalanche']['monthly_outlay'])
check('and finishes sooner', d2['avalanche']['months'] < d['avalanche']['months'],
      (d['avalanche']['months'], d2['avalanche']['months']))
check('with less interest', d2['avalanche']['total_interest'] < d['avalanche']['total_interest'],
      (d['avalanche']['total_interest'], d2['avalanche']['total_interest']))
check('avalanche clears the 25% card before the 7% loan',
      d2['avalanche']['order'][0]['name'] == 'Visa', d2['avalanche']['order'])
check('snowball clears the smaller balance first',
      d2['snowball']['order'][0]['name'] == 'Visa', d2['snowball']['order'])
check('a query override does not need to be saved',
      me.get('/api/finance/debt-plan?extra=0').get_json()['extra_monthly'] == 0.0)
check('and does not overwrite the saved figure',
      me.get('/api/finance/debt-plan').get_json()['extra_monthly'] == 300.0)
check('a nonsense extra is rejected',
      me.get('/api/finance/debt-plan?extra=lots').status_code == 400)
check('a negative extra is clamped, not applied',
      me.get('/api/finance/debt-plan?extra=-500').get_json()['extra_monthly'] == 0.0)
check('signed-out requests are refused',
      app.test_client().get('/api/finance/debt-plan').status_code in (401, 302))

print('\n--- the overview and the briefing carry it ---')
obs = {o['key']: o for o in me.get('/api/finance/overview').get_json()['observations']}
check('the uncovered debt is reported as missing from cash flow',
      'debt_not_in_cashflow' in obs, list(obs))
check('and it names the amount', obs['debt_not_in_cashflow']['amount'] == 180.0,
      obs['debt_not_in_cashflow'])
check('high-rate debt is raised exactly once, not by two modules',
      len([k for k in obs if 'high' in k and ('rate' in k or 'apr' in k)]) == 1,
      [k for k in obs if 'high' in k])
with app.app_context():
    pic = A._finance_full_picture(1)
    facts = A._overview_facts(pic, A._finance_observations(pic))
check('the briefing has a payoff section', '== DEBT PAYOFF PLAN ==' in facts)
check('it names the payoff order on one line, not one line per debt',
      'Payoff order: Visa (month' in facts,
      [l for l in facts.split('\n') if 'Payoff order' in l])
check('it quantifies the strategy difference', 'difference' in facts,
      [l for l in facts.split('\n') if 'difference' in l])
check('the outflow line explains the dedupe, so the model does not think a payment is lost',
      'not added' in facts, [l for l in facts.split('\n') if 'outflow' in l])

print('\n--- a debt whose minimum cannot cover its interest ---')
with app.app_context():
    db.session.add(A.Debt(id=7, user_id=1, name='Payday', type='personal',
                          balance=5000, apr=99.0, min_payment=50))
    db.session.commit()
d3 = me.get('/api/finance/debt-plan?extra=0').get_json()
check('no payoff date is invented', d3['avalanche']['months'] is None, d3['avalanche']['months'])
check('the debt is named', [n['name'] for n in d3['avalanche']['never_pays_off']] == ['Payday'],
      d3['avalanche']['never_pays_off'])
obs = {o['key']: o for o in me.get('/api/finance/overview').get_json()['observations']}
check('and it is raised as critical',
      obs.get('never_pays_off:7', {}).get('severity') == 'critical', list(obs))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL DEBT API CHECKS PASSED')
