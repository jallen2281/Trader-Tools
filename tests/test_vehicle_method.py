"""One vehicle, one method -- and the farm exception that makes the rule worth stating.

The standard mileage rate is not a fuel allowance. It already contains fuel, oil, repairs,
insurance and depreciation, so a car-and-truck expense row filed to a book that also logs
trips deducts the same mile twice. app.py has said so in a category label since the
Schedule C set was added -- 'biz_car_truck': 'Car and truck, actual expenses (not with
standard mileage)' -- and never checked: _business_books subtracts `expenses` and
`mileage` from the same book without ever comparing them, so the overlap cannot be seen in
the one figure anyone reads.

Found the live way round. This install's realty book was deducting 631 miles on a 2024
Silverado 2500 and holding zero spend rows, while diesel for that same truck sat unfiled.
Filing it to the realty book -- the obvious thing to do with a fuel receipt for a work
trip -- would have quietly double-counted it.

THE EXCEPTION IS THE INTERESTING HALF. Schedule F splits the two on purpose: line 10 "Car
and truck" is the vehicle, line 14 "Gasoline, fuel and oil" is the equipment. A farm that
logs truck miles and buys tractor diesel is correct in both places, because off-road
equipment has no mileage option to conflict with. A guard that flagged that pairing would
cry wolf on the commonest farm arrangement there is -- including this one -- so farm_fuel
is deliberately outside VEHICLE_ACTUAL_CATEGORIES, and the test below pins it there.

It warns and does not block, and it never touches net: which method to keep is the user's
call, the books cannot tell which vehicle a receipt belongs to, and a guard people route
around is worse than a warning they read.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='vehmethod_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'v.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
os.environ['TT_BACKGROUND_JOBS'] = '0'
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


YR = 2026
JAN, DEC = date(YR, 1, 1), date(YR, 12, 31)

print('\n--- the category set says which costs collide with the rate ---')
check('the business vehicle line is in it', 'biz_car_truck' in A.VEHICLE_ACTUAL_CATEGORIES)
check('so is the farm vehicle line', 'farm_car_truck' in A.VEHICLE_ACTUAL_CATEGORIES)
check('FARM FUEL IS NOT -- tractor diesel is Schedule F line 14, not a vehicle',
      'farm_fuel' not in A.VEHICLE_ACTUAL_CATEGORIES)
check('nor is plain transportation, which is a household category',
      'transportation' not in A.VEHICLE_ACTUAL_CATEGORIES)
check('every member is a real category',
      all(c in A.BUDGET_CATEGORIES for c in A.VEHICLE_ACTUAL_CATEGORIES))

with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='u1@x.com', name='U', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    realty = A.Entity(user_id=1, name='Coldwell Banker Realty', kind='business',
                      tax_form='Schedule C')
    farm = A.Entity(user_id=1, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    db.session.add_all([realty, farm])
    db.session.flush()
    REALTY, FARM = realty.id, farm.id
    PROF = A.TaxProfile(user_id=1, filing_status='mfj')
    db.session.add(PROF)
    db.session.commit()

    def trip(eid, miles, when, vehicle='2024 Silverado 2500'):
        t = A.MileageLog(user_id=1, entity_id=eid, trip_date=when, miles=miles,
                         purpose='Showing', vehicle=vehicle)
        db.session.add(t)
        db.session.commit()
        return t

    def spend(eid, amount, cat, when=date(YR, 10, 30), desc='MUDFLAP'):
        t = A.SpendTransaction(user_id=1, entity_id=eid, posted_at=when, description=desc,
                               category=cat, amount=amount)
        db.session.add(t)
        db.session.commit()
        return t

    def conflict(eid):
        return A._vehicle_method_conflict(1, eid, JAN, DEC)

    print('\n--- mileage alone is not a conflict ---')
    trip(REALTY, 106.0, date(YR, 5, 9))
    trip(REALTY, 120.0, date(YR, 7, 11))
    check('two trips logged, nothing claimed twice', conflict(REALTY) is None, conflict(REALTY))

    print('\n--- an expense row alone is not a conflict either ---')
    # No trips on the farm book yet, so actual expenses are the farm's only method and
    # therefore a perfectly valid election.
    farm_truck = spend(FARM, 240.00, 'farm_car_truck', desc='Truck tyres')
    check('actual expenses with no mileage are a valid election',
          conflict(FARM) is None, conflict(FARM))

    print('\n--- both, on the same book, is the bug ---')
    fuel = spend(REALTY, 163.87, 'biz_car_truck', desc='MUDFLAP')
    c = conflict(REALTY)
    check('it is flagged', c is not None)
    check('it reports the miles', c and c['miles'] == 226.0, c)
    check('and what the rate already paid for them',
          c and c['mileage_deduction'] == round(106.0 * 0.725 + 120.0 * 0.76, 2), c)
    check('it counts the colliding rows', c and c['expense_rows'] == 1, c)
    check('and their total', c and c['expense_total'] == 163.87, c)
    check('it names the category', c and c['categories'] == ['biz_car_truck'], c)
    check('it points at the actual rows, so they can be fixed',
          c and c['spend_ids'] == [fuel.id], c)
    check('it names the vehicle, because the election is per vehicle',
          c and c['vehicles'] == ['2024 Silverado 2500'], c)
    check('the message says the cost is counted twice',
          c and 'twice' in c['message'], c and c['message'])
    check('and tells you the rate already includes fuel',
          c and 'includes fuel' in c['message'], c and c['message'])

    print('\n--- THE FARM EXCEPTION: truck miles and tractor diesel coexist ---')
    db.session.delete(farm_truck)
    db.session.commit()
    trip(FARM, 40.0, date(YR, 6, 20), vehicle='2024 Silverado 2500')
    diesel = spend(FARM, 158.26, 'farm_fuel', desc='MUDFLAP', when=date(YR, 9, 15))
    check('TRACTOR DIESEL BESIDE TRUCK MILES IS NOT FLAGGED',
          conflict(FARM) is None, conflict(FARM))
    check('and it really is in the book, not merely absent',
          db.session.get(A.SpendTransaction, diesel.id).category == 'farm_fuel')
    # ...but the farm's own vehicle line still collides, exactly as the business one does.
    tyres = spend(FARM, 240.00, 'farm_car_truck', desc='Truck tyres')
    c = conflict(FARM)
    check('the farm VEHICLE line does collide with the farm truck miles', c is not None, c)
    check('and only the vehicle row is named, not the diesel',
          c and c['spend_ids'] == [tyres.id], c)
    check('the diesel is not counted in the total', c and c['expense_total'] == 240.00, c)

    print('\n--- a trip outside the window does not raise it ---')
    db.session.delete(tyres)
    db.session.commit()
    check("last year's mileage cannot conflict with this year's expenses",
          A._vehicle_method_conflict(1, REALTY, date(YR - 1, 1, 1), date(YR - 1, 12, 31))
          is None)

    print('\n--- _business_books surfaces it without changing a single figure ---')
    bb = A._business_books(1, YR, PROF)
    rows = {r['name']: r for r in bb['entities']}
    r = rows['Coldwell Banker Realty']
    check('the row carries the warning', r['vehicle_conflict'] is not None, r['vehicle_conflict'])
    check('the farm row does not -- diesel only',
          rows['Chicken Tales LLC']['vehicle_conflict'] is None,
          rows['Chicken Tales LLC']['vehicle_conflict'])
    check('the conflicts are hoisted for a caller showing one headline',
          len(bb['vehicle_conflicts']) == 1, bb['vehicle_conflicts'])
    check('each hoisted one says which book it belongs to',
          bb['vehicle_conflicts'][0]['entity'] == 'Coldwell Banker Realty'
          and bb['vehicle_conflicts'][0]['entity_id'] == REALTY, bb['vehicle_conflicts'][0])

    # The whole point of "warn, don't block": the arithmetic is untouched.
    check('NET STILL SUBTRACTS BOTH -- the warning does not silently fix it',
          r['net_actual'] == round(r['income_actual'] - r['expenses'] - r['mileage_deduction'], 2),
          (r['net_actual'], r['income_actual'], r['expenses'], r['mileage_deduction']))
    check('the double-counted row is still in expenses', r['expenses'] >= 163.87, r['expenses'])
    check('and the mileage is still deducted in full',
          r['mileage_deduction'] == round(106.0 * 0.725 + 120.0 * 0.76, 2), r['mileage_deduction'])

    print('\n--- the list is always a list ---')
    bb2 = A._business_books(1, YR, PROF)
    check('vehicle_conflicts is a list, never None, so `if conflicts:` always reads right',
          isinstance(bb2['vehicle_conflicts'], list), type(bb2['vehicle_conflicts']))

    print('\n--- and it survives the entered-figure path, which returns early ---')
    PROF.business_net_annual = 5000.0
    db.session.commit()
    bb3 = A._business_books(1, YR, PROF)
    check('an entered business net still reports the conflict',
          len(bb3.get('vehicle_conflicts', [])) == 1, bb3.get('vehicle_conflicts'))
    check('and still says the net came from the profile', bb3['source'] == 'entered', bb3['source'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL VEHICLE METHOD CHECKS PASSED')
