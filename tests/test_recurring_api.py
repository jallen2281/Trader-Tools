"""Recurring-charge detection wired into the application.

test_recurring.py covers the arithmetic in isolation. This covers what the arithmetic is
attached to: that a detected charge can be turned into a real bill, that a decision about it
survives a recompute, that one person's dismissal does not silence their partner's view, and
that the overview and the AI briefing both know about it.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

TMP = tempfile.mkdtemp(prefix='recapi_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'r.db').replace(os.sep, '/')
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


def txns(user_id, merchant, amount, every_days, count, category='subscriptions',
         share_level='none', end=None):
    """Charges laid backwards from `end` so the most recent one is always near today —
    otherwise every fixture would read as 'stopped' whenever the suite is run."""
    end = end or TODAY
    out = []
    for i in range(count):
        amt = amount(i) if callable(amount) else amount
        out.append(A.SpendTransaction(
            user_id=user_id, posted_at=end - timedelta(days=every_days * i),
            description=merchant, merchant=merchant, amount=amt, category=category,
            source='csv', share_level=share_level,
            external_id='%s-%s-%d' % (user_id, merchant, i)))
    return out


with app.app_context():
    db.drop_all()
    db.create_all()
    now = A.datetime.utcnow()
    V = A.CONSENT_VERSION
    db.session.add_all([
        A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=2, google_id='g2', email='partner@x.com', name='Partner', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
    ])
    db.session.flush()
    db.session.add_all(
        # undeclared, and the expensive one
        txns(1, 'ACME CLOUD BACKUP', 39.99, 30, 8)
        # undeclared and quietly more expensive than it was
        + txns(1, 'STREAMFLIX', lambda i: 9.99 if i >= 3 else 15.99, 30, 8)
        # declared as a bill below, so it must never be reported
        + txns(1, 'CITY WATER DEPT', 62.0, 30, 7, category='utilities')
        # noise: same shop, wildly different amounts — must not be called a subscription
        + txns(1, 'FOODMART 88', lambda i: 30 + i * 17, 6, 12, category='food')
    )
    db.session.add(A.RecurringBill(id=20, user_id=1, name='Water', payee='CITY WATER DEPT',
                                   category='utilities', amount=62, frequency='monthly',
                                   active=True))
    db.session.commit()

me, partner = client_for(1), client_for(2)


def scan(c=None):
    return (c or me).get('/api/finance/recurring').get_json()


def by_key(d):
    return {c['merchant_key']: c for c in d['charges']}


print('\n--- the ledger is scanned and the obvious things are found ---')
d = scan()
keys = by_key(d)
check('the cloud backup is detected', 'ACME CLOUD' in keys, list(keys))
check('so is the streaming service', 'STREAMFLIX' in keys, list(keys))
check('and the declared utility bill', 'CITY WATER' in keys, list(keys))
check('the supermarket is NOT called a subscription', 'FOODMART' not in keys, list(keys))
check('cadence read as monthly', keys['ACME CLOUD']['cadence'] == 'monthly',
      keys['ACME CLOUD']['cadence'])
check('typical amount is the observed one', keys['ACME CLOUD']['typical_amount'] == 39.99,
      keys['ACME CLOUD']['typical_amount'])

print('\n--- a charge already declared as a bill is not reported as missing ---')
check('the water bill is matched to bill 20', keys['CITY WATER']['matched_bill_id'] == 20,
      keys['CITY WATER'])
kinds = {(f['kind'], f['merchant_key']) for f in d['findings']}
check('so nothing is raised about it', ('undeclared', 'CITY WATER') not in kinds, kinds)
check('but the cloud backup IS raised', ('undeclared', 'ACME CLOUD') in kinds, kinds)
check('and the price rise is raised', ('price_increase', 'STREAMFLIX') in kinds, kinds)
check('undeclared total counts only what is unbilled',
      round(d['undeclared_annual']) == round(keys['ACME CLOUD']['annual_equivalent']
                                             + keys['STREAMFLIX']['annual_equivalent']),
      (d['undeclared_annual'], d['undeclared_count']))

print('\n--- dismissing one silences it, and the decision survives a rescan ---')
r = me.post('/api/finance/recurring/decision',
            json={'merchant_key': 'ACME CLOUD', 'decision': 'dismissed'})
check('the decision is accepted', r.status_code == 200, r.get_json())
d2 = scan()
check('it stops being raised',
      ('undeclared', 'ACME CLOUD') not in {(f['kind'], f['merchant_key']) for f in d2['findings']},
      d2['findings'])
check('but it is still listed, marked dismissed',
      by_key(d2)['ACME CLOUD']['decision'] == 'dismissed')
check('and it no longer counts toward the undeclared total',
      d2['undeclared_annual'] < d['undeclared_annual'],
      (d['undeclared_annual'], d2['undeclared_annual']))

print('\n--- a decision is one person\'s, not the household\'s ---')
with app.app_context():
    h = A.Household(name='Home', created_by=1)
    db.session.add(h)
    db.session.flush()
    db.session.add_all([A.HouseholdMember(household_id=h.id, user_id=1, role='owner',
                                          status='active', invited_email='me@x.com'),
                        A.HouseholdMember(household_id=h.id, user_id=2, role='member',
                                          status='active', invited_email='partner@x.com')])
    for t in A.SpendTransaction.query.filter_by(user_id=1).all():
        t.share_level = 'view'
    db.session.commit()
dp = scan(partner)
check('the partner sees the shared charges', 'ACME CLOUD' in by_key(dp), list(by_key(dp)))
check('my dismissal does not silence it for them',
      by_key(dp)['ACME CLOUD']['decision'] is None, by_key(dp)['ACME CLOUD'].get('decision'))
check('so they are still told about it',
      ('undeclared', 'ACME CLOUD') in {(f['kind'], f['merchant_key']) for f in dp['findings']})

print('\n--- clearing a decision puts it back ---')
r = me.post('/api/finance/recurring/decision',
            json={'merchant_key': 'ACME CLOUD', 'decision': ''})
check('clearing is accepted', r.status_code == 200 and r.get_json()['decision'] is None,
      r.get_json())
check('and it is raised again',
      ('undeclared', 'ACME CLOUD') in {(f['kind'], f['merchant_key']) for f in scan()['findings']})

print('\n--- adopting turns a detection into a real bill ---')
before = me.get('/api/finance/bills').get_json()['total_monthly']
r = me.post('/api/finance/recurring/adopt', json={'merchant_key': 'ACME CLOUD'})
check('adopt succeeds', r.status_code == 201, (r.status_code, r.get_json()))
bill = r.get_json()['bill']
check('the bill carries the observed amount', bill['amount'] == 39.99, bill)
check('and the observed cadence', bill['frequency'] == 'monthly', bill)
check('and a due date in the future', bill['next_due_date'] >= TODAY.isoformat(),
      bill['next_due_date'])
check('it categorises as a subscription', bill['category'] == 'subscriptions', bill)
after = me.get('/api/finance/bills').get_json()['total_monthly']
check('the monthly bill total goes up by the charge', round(after - before, 2) == 39.99,
      (before, after))
d3 = scan()
check('the charge is now linked to that bill',
      by_key(d3)['ACME CLOUD']['matched_bill_id'] == bill['id'], by_key(d3)['ACME CLOUD'])
check('and is no longer reported as undeclared',
      ('undeclared', 'ACME CLOUD') not in {(f['kind'], f['merchant_key']) for f in d3['findings']})

print('\n--- the API refuses what it should ---')
check('an unknown merchant cannot be adopted',
      me.post('/api/finance/recurring/adopt', json={'merchant_key': 'NOPE'}).status_code == 404)
check('adopt needs a merchant_key',
      me.post('/api/finance/recurring/adopt', json={}).status_code == 400)
check('an invented decision is rejected',
      me.post('/api/finance/recurring/decision',
              json={'merchant_key': 'STREAMFLIX', 'decision': 'maybe'}).status_code == 400)
check('a decision needs a merchant_key',
      me.post('/api/finance/recurring/decision', json={'decision': 'dismissed'}).status_code == 400)
with app.app_context():
    db.session.add(A.RecurringBill(id=99, user_id=2, name='Not mine', amount=5,
                                   frequency='monthly', active=True, share_level='none'))
    db.session.commit()
r = me.post('/api/finance/recurring/decision',
            json={'merchant_key': 'STREAMFLIX', 'decision': 'linked', 'bill_id': 99})
check('linking to a bill I cannot see is a 404, not a leak', r.status_code == 404, r.get_json())
check('signed-out requests are refused',
      app.test_client().get('/api/finance/recurring').status_code in (401, 302))

print('\n--- the overview and the briefing both know about it ---')
obs = {o['key']: o for o in me.get('/api/finance/overview').get_json()['observations']}
check('undeclared subscriptions are flagged', 'undeclared_subscriptions' in obs, list(obs))
check('the price rise is a warning, named by merchant',
      obs.get('price_increase:STREAMFLIX', {}).get('severity') == 'warning',
      [k for k in obs if k.startswith('price_increase')])
with app.app_context():
    pic = A._finance_full_picture(1)
    facts = A._overview_facts(pic, A._finance_observations(pic))
check('the briefing has a recurring section', '== RECURRING CHARGES DETECTED' in facts)
check('and names a charge the model can reason about', 'STREAMFLIX' in facts,
      [l for l in facts.split('\n') if 'STREAM' in l])
check('and says which are not declared bills', 'NOT a declared bill' in facts,
      [l for l in facts.split('\n') if 'declared bill' in l])

print('\n--- a charge that stopped is surfaced ---')
with app.app_context():
    db.session.add_all(txns(1, 'OLD GYM', 45.0, 30, 6,
                            category='personal', end=TODAY - timedelta(days=120)))
    db.session.commit()
d4 = scan()
check('marked stopped rather than active', by_key(d4)['OLD GYM']['status'] == 'stopped',
      by_key(d4).get('OLD GYM'))
check('and reported', ('stopped', 'OLD GYM') in {(f['kind'], f['merchant_key']) for f in d4['findings']},
      d4['findings'])
check('a stopped charge is not counted in the monthly total',
      all(c['merchant_key'] != 'OLD GYM' or c['status'] == 'stopped' for c in d4['charges'])
      and d4['monthly_total'] < sum(c['monthly_equivalent'] for c in d4['charges']),
      d4['monthly_total'])
obs = {o['key']: o for o in me.get('/api/finance/overview').get_json()['observations']}
check('the overview mentions it too', 'stopped_charges' in obs, list(obs))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL RECURRING API CHECKS PASSED')
