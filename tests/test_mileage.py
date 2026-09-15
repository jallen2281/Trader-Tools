"""A mileage log and Schedule C books for a real estate business.

An agent's biggest deduction is usually the driving -- showings, listings, closings -- and
the IRS only accepts it with a record made at the time: date, where, why, how far. So a
trip is one row with a required purpose, and its deduction uses the rate in force on its
date, because 2026 changed rates mid-year (72.5 cents to 76 from July 1).

The books feed the tax estimate, and two businesses can belong to two people: a farm loss
on one spouse's Schedule F must not erase the self-employment tax on the other's commissions.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='miles_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'm.db').replace(os.sep, '/')
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


print('\n--- the rate is the one in force on the day ---')
check('2025: 70 cents', A.mileage_rate(date(2025, 11, 3)) == 0.70)
check('2026 through June 30: 72.5 cents', A.mileage_rate(date(2026, 6, 30)) == 0.725)
check('from July 1, 2026: 76 cents', A.mileage_rate(date(2026, 7, 1)) == 0.76)

print('\n--- Schedule C categories exist and read as the form does ---')
check('a business book offers them', 'business' in A.ENTITY_CATEGORY_SETS)
check('accepted anywhere a category is', 'biz_meals' in A.BUDGET_CATEGORIES
      and 'biz_dues_subscriptions' in A.BUDGET_CATEGORIES)
check('labelled for people', A.category_label('biz_dues_subscriptions').startswith('Dues and subscriptions'))

with app.app_context():
    db.drop_all()
    db.create_all()
    for uid in (1, 2):
        db.session.add(A.User(id=uid, google_id='g%d' % uid, email='u%d@x.com' % uid, name='U',
                              role='admin', privacy_consent_at=A.datetime.utcnow(),
                              privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    realty = A.Entity(user_id=1, name='Coldwell Banker Realty', kind='business', tax_form='Schedule C')
    farm = A.Entity(user_id=1, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    theirs = A.Entity(user_id=2, name='Not yours', kind='business', tax_form='Schedule C')
    db.session.add_all([realty, farm, theirs])
    db.session.flush()
    REALTY, FARM, THEIRS = realty.id, farm.id, theirs.id
    db.session.add(A.TaxProfile(user_id=1, filing_status='mfj'))
    db.session.add(A.IncomeSource(user_id=1, name='Salary', type='salary', annual_salary=90000,
                                  pay_frequency='biweekly', tax_form='W2', owner='me', active=True))
    db.session.add(A.IncomeSource(user_id=1, name='Coldwell Banker commission', type='other',
                                  irregular=True, estimated_annual=12000, tax_form='1099',
                                  entity_id=REALTY, active=True))
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True


def trip(**kw):
    body = {'trip_date': '2026-09-15', 'purpose': 'Showing at 412 Elm', 'miles': 18.5,
            'entity_id': REALTY}
    body.update(kw)
    return c.post('/api/finance/mileage', json=body)


print('\n--- logging trips ---')
r = trip(round_trip=True, origin='Home', destination='412 Elm St', vehicle='2024 Silverado HD')
check('saves', r.status_code == 201, r.get_json())
t = r.get_json()
check('a round trip doubles the one-way miles', t['total_miles'] == 37.0, t)
check('at the September rate', t['rate'] == 0.76 and t['deduction'] == round(37.0 * 0.76, 2), t)
r = trip(trip_date='2026-03-02', miles=None, start_odometer=40210.4, end_odometer=40262.9,
         purpose='Listing appointment')
t = r.get_json()
check('odometer readings give the distance', t['total_miles'] == 52.5, t)
check('at the March rate', t['rate'] == 0.725, t)
trip(trip_date='2026-05-10', miles=12, entity_id=FARM, purpose='Feed pickup')

print('\n--- a log the IRS would reject is refused ---')
for label, kw in (('no purpose', {'purpose': '   '}),
                  ('zero miles', {'miles': 0}),
                  ('odometer running backwards', {'miles': None, 'start_odometer': 500, 'end_odometer': 400}),
                  ('no date', {'trip_date': ''}),
                  ('a 3,000 mile typo', {'miles': 3000}),
                  ("someone else's books", {'entity_id': THEIRS})):
    r = trip(**kw)
    check('%-28s -> 400' % label, r.status_code == 400, (r.status_code, r.get_json()))

print('\n--- the year view ---')
d = c.get('/api/finance/mileage?year=2026').get_json()
check('three trips', d['count'] == 3, d['count'])
check('total miles', d['totals']['miles'] == 37.0 + 52.5 + 12, d['totals'])
check("total deduction uses each date's rate",
      d['totals']['deduction'] == round(37 * 0.76 + 52.5 * 0.725 + 12 * 0.725, 2), d['totals'])
realty_row = [b for b in d['by_book'] if b['entity_id'] == REALTY][0]
check('split by book', realty_row['miles'] == 89.5 and realty_row['trips'] == 2, realty_row)
check('vehicles offered for next time', d['vehicles'] == ['2024 Silverado HD'], d['vehicles'])
check('another year is empty', c.get('/api/finance/mileage?year=2025').get_json()['count'] == 0)

print('\n--- editing and deleting ---')
tid = d['trips'][0]['id']
r = c.put('/api/finance/mileage/%d' % tid, json={'round_trip': False})
check('edit recalculates', r.get_json()['total_miles'] == 18.5, r.get_json())
with c.session_transaction() as sess:
    sess['_user_id'] = '2'
check("someone else can't edit it", c.put('/api/finance/mileage/%d' % tid, json={'miles': 1}).status_code == 404)
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
c.put('/api/finance/mileage/%d' % tid, json={'round_trip': True})

print('\n--- the realty books ---')
with app.app_context():
    db.session.add_all([
        A.SpendTransaction(user_id=1, entity_id=REALTY, posted_at=date(2026, 4, 2), description='MLS dues',
                           category='biz_dues_subscriptions', amount=400),
        A.SpendTransaction(user_id=1, entity_id=REALTY, posted_at=date(2026, 6, 9), description='Client lunch',
                           category='biz_meals', amount=80),
        A.SpendTransaction(user_id=1, entity_id=FARM, posted_at=date(2026, 5, 1), description='Coop build',
                           category='farm_supplies', amount=20000),
    ])
    db.session.commit()
    books = A._business_books(1, 2026, A._tax_profile(1))
rows = {r['name']: r for r in books['entities']}
re = rows['Coldwell Banker Realty']
mil = round(37 * 0.76 + 52.5 * 0.725, 2)
check('meals count at half', re['expenses'] == 400 + 40, re['expenses'])
check('mileage is its own line', re['mileage_deduction'] == mil, re)
check('net = commissions - expenses - mileage', re['net'] == round(12000 - 440 - mil, 2), re['net'])

print("\n--- one business's loss does not erase the other's self-employment tax ---")
farm_net = rows['Chicken Tales LLC']['net']
check('the farm is deep in the red', farm_net < -19000, farm_net)
check('combined, the books are a loss', books['net'] < 0, books['net'])
check('but SE is still owed on the realty profit', books['se_profit'] == re['net'], books['se_profit'])
with app.app_context():
    e = A._income_tax_estimate(1)
check('the estimate charges it', e['self_employment_tax_return'] > 0, e['self_employment_tax_return'])
check('and the commission is not also counted as freestanding 1099 income', e['se_income'] == 0.0, e['se_income'])

print('\n--- where it shows ---')
rep = c.get('/api/finance/entities/report?year=2026').get_json()
rr = [x for x in rep['entities'] if x['entity']['name'] == 'Coldwell Banker Realty'][0]
check('the Books card reports the mileage', rr['mileage_deduction'] == mil, rr)
cats = c.get('/api/finance/entities').get_json()['category_sets']
check('the form is offered Schedule C lines for a business', any(o['value'] == 'biz_meals' for o in cats['business']))
body = c.get('/finances').get_data(as_text=True)
check('mileage card on the page', 'id="mileageBody"' in body and 'openTrip(' in body)
check('category group named for the schedule', "business: 'Schedule C'" in body)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL MILEAGE CHECKS PASSED')
