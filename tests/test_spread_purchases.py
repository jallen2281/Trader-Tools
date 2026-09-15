"""A bulk purchase counts in the budget across the months it covers.

A propane prebuy for the winter, a pallet of feed that lasts a season: paid once, used for
months. Counted against the month it cleared, it blew that month's budget and left the
months it actually fed looking cheap. Spread, the budget takes an equal share of it in
each month covered -- while the cash ledger and the farm's tax books keep the payment
date, because the money really left that day and the return is on the cash method.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='spread_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 's.db').replace(os.sep, '/')
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
    db.session.add(A.User(id=1, google_id='g1', email='u@x.com', name='U', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True


def mk(**kw):
    body = {'description': 'x', 'amount': 100, 'category': 'other', 'posted_at': '2026-09-10'}
    body.update(kw)
    return c.post('/api/finance/transactions', json=body)


def month(ym, cat):
    with app.app_context():
        rows = {r['category']: r for r in A._budget_rollup(1, ym)}
    return rows.get(cat, {})


print('\n--- a propane prebuy: paid in September for October through March ---')
r = mk(description='Propane prebuy', amount=1800, category='utilities',
       spread_months=6, spread_start='2026-10')
check('saves', r.status_code == 201, r.get_json())
t = r.get_json()
check('reports its window', (t['spread_start'], t['spread_end']) == ('2026-10', '2027-03'),
      (t['spread_start'], t['spread_end']))
check('September -- the month it was paid -- carries none of it',
      month('2026-09', 'utilities').get('actual_monthly', 0) == 0, month('2026-09', 'utilities'))
check('October carries a sixth', month('2026-10', 'utilities')['actual_monthly'] == 300,
      month('2026-10', 'utilities'))
check('so does March, across the year boundary', month('2027-03', 'utilities')['actual_monthly'] == 300,
      month('2027-03', 'utilities'))
check('April is past the winter', month('2027-04', 'utilities').get('actual_monthly', 0) == 0)
check('the budget card can say how much of October is a bulk buy',
      month('2026-10', 'utilities')['spread_monthly'] == 300, month('2026-10', 'utilities'))

print('\n--- bulk feed, starting the month it was bought ---')
r = mk(description='Bulk layer feed', amount=1000, category='farm_feed', posted_at='2026-09-01',
       spread_months=3)
t = r.get_json()
check('no start month means the month paid', t['spread_start'] == '2026-09', t['spread_start'])
shares = [month(m, 'farm_feed').get('actual_monthly', 0) for m in ('2026-09', '2026-10', '2026-11')]
check('equal shares, the last one taking the rounding', shares == [333.33, 333.33, 333.34], shares)
check('which add back to exactly what was paid', round(sum(shares), 2) == 1000.0, sum(shares))

print('\n--- an ordinary purchase is untouched ---')
mk(description='Wegmans', amount=120, category='food', posted_at='2026-10-05')
check('counts in full in its month', month('2026-10', 'food')['actual_monthly'] == 120)
check('and nowhere else', month('2026-11', 'food').get('actual_monthly', 0) == 0)
check('with no spread portion', month('2026-10', 'food')['spread_monthly'] == 0)

print('\n--- the cash ledger keeps the payment date ---')
j = c.get('/api/finance/transactions?month=2026-09').get_json()
check('September lists the whole $1,800 prebuy -- the money left then',
      any(x['description'] == 'Propane prebuy' and x['amount'] == 1800 for x in j['transactions']))
check('and totals it as cash out that month', j['total'] >= 1800 + 1000, j['total'])

print('\n--- the farm books keep the payment date too ---')
with app.app_context():
    farm = A.Entity(user_id=1, name='Farm', kind='farm', tax_form='Schedule F')
    db.session.add(farm)
    db.session.flush()
    db.session.add(A.SpendTransaction(user_id=1, entity_id=farm.id, posted_at=date(2026, 12, 20),
                                      description='Feed pallet', category='farm_feed',
                                      amount=2400, spread_months=6))
    db.session.commit()
    prof = A._tax_profile(1)
    books_2026 = A._business_books(1, 2026, prof)
    books_2027 = A._business_books(1, 2027, prof)
check('the whole pallet is a 2026 expense -- the year it was paid',
      books_2026['books_net_so_far'] == -2400, books_2026)
check('none of it lands in 2027', books_2027['books_net_so_far'] == 0, books_2027)
check('while the 2027 budget still carries its share',
      month('2027-01', 'farm_feed')['actual_monthly'] == 400, month('2027-01', 'farm_feed'))

print('\n--- bad input is refused, not guessed at ---')
for label, kw in (('zero months', {'spread_months': 0}),
                  ('37 months', {'spread_months': 37}),
                  ('not a number', {'spread_months': 'winter'}),
                  ('a start that is not a month', {'spread_months': 3, 'spread_start': 'soon'})):
    r = mk(**kw)
    check('%-28s -> 400' % label, r.status_code == 400, (r.status_code, r.get_json()))

print('\n--- editing it back to a normal purchase ---')
tid = mk(description='Undo', amount=600, category='utilities', posted_at='2026-11-02',
         spread_months=3, spread_start='2026-12').get_json()['id']
r = c.put('/api/finance/transactions/%d' % tid, json={'spread_months': 1})
t = r.get_json()
check('one month clears the spread', t['spread_months'] is None, t)
check('and the start month with it', t['spread_start'] is None, t)
check('it counts in November again', month('2026-11', 'utilities')['actual_monthly'] >= 600,
      month('2026-11', 'utilities'))

print('\n--- a spread transfer is still not spending ---')
mk(description='Moved money', amount=5000, category='transfer', spread_months=5)
check('no transfer line in any month', not month('2026-10', 'transfer'))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL SPREAD-PURCHASE CHECKS PASSED')
